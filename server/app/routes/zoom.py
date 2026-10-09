import json
import secrets
import time

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import audit, models, ratelimit, zoom
from ..db import get_db
from ..deps import client_ip, current_user, meeting_for, require_role, scoped_cookie
from ..security import decrypt, encrypt
from ..settings import settings

router = APIRouter(tags=["zoom"])
PENDING_SECONDS = 900


class ZoomImportIn(BaseModel):
    uuid: str
    recording: bool = False


class ClaimIn(BaseModel):
    org_id: str


def optional_user(request, db):
    try:
        return current_user(request, db)
    except HTTPException:
        return None


def cookie_opts(max_age=None):
    opts = {"httponly": True, "samesite": "lax", "secure": settings.secure_cookies, "path": "/api/zoom"}
    if max_age is not None:
        opts["max_age"] = max_age
    return opts


def forget(resp, name):
    resp.delete_cookie(scoped_cookie(name), **cookie_opts())
    return resp


def save_connection(db, request, user, org_id, tok, who):
    c = db.scalar(select(models.ZoomConnection).where(models.ZoomConnection.org_id == org_id))
    if c is None:
        c = models.ZoomConnection(org_id=org_id, token_enc="", created_by=user.id)
        db.add(c)
    c.token_enc = encrypt(json.dumps(tok))
    c.host_email = who.get("email", "")
    c.zoom_user_id = who.get("id", "")
    c.zoom_account_id = who.get("account_id", "")
    audit.log(db, "zoom.connected", user, org_id, client_ip(request), host=c.host_email)
    return c


def purge_pending(db):
    for row in db.scalars(select(models.ZoomPending).where(models.ZoomPending.expires_at < time.time())).all():
        try:
            zoom.revoke_token(json.loads(decrypt(row.token_enc)).get("access_token", ""))
        except (ValueError, json.JSONDecodeError):
            pass
        db.delete(row)


def pending_row(request, db):
    try:
        pid = decrypt(request.cookies.get(scoped_cookie("lm_zoom_pending"), ""))
    except ValueError:
        pid = ""
    row = db.get(models.ZoomPending, pid) if pid else None
    if row is None or row.expires_at < time.time():
        raise HTTPException(404, "no Zoom account is waiting to be connected; start again from Settings")
    return row


def eligible(db, user):
    rows = db.execute(select(models.Organization).join(models.Membership, models.Membership.org_id == models.Organization.id)
                      .where(models.Membership.user_id == user.id).order_by(models.Organization.name)).scalars().all()
    out = []
    for org in rows:
        try:
            require_role(db, user, org.id, "secretary")
        except HTTPException:
            continue
        out.append(org)
    return out


def connection(db, org_id):
    c = db.scalar(select(models.ZoomConnection).where(models.ZoomConnection.org_id == org_id))
    if c is None:
        raise HTTPException(400, "Zoom is not connected for this organization")
    return c


@router.get("/api/orgs/{org_id}/zoom")
def status(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, org_id, "member")
    c = db.scalar(select(models.ZoomConnection).where(models.ZoomConnection.org_id == org_id))
    org = db.get(models.Organization, org_id)
    return {"available": zoom.configured(), "connected": c is not None, "host_email": c.host_email if c else "",
            "auto_import": bool(((org.settings if org else None) or {}).get("zoom_auto_import"))}


class AutoImportIn(BaseModel):
    on: bool


@router.put("/api/orgs/{org_id}/zoom/auto-import")
def set_auto_import(org_id: str, body: AutoImportIn, request: Request, user: models.User = Depends(current_user),
                    db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "secretary")
    cfg = dict(org.settings or {})
    cfg["zoom_auto_import"] = bool(body.on)
    org.settings = cfg
    audit.log(db, "zoom.auto_import", user, org_id, client_ip(request), on=bool(body.on))
    db.commit()
    return {"auto_import": bool(body.on)}


AUTO_EVENTS = ("recording.completed", "recording.transcript_completed")


def auto_import(conn_id, uuid, event):
    from ..db import SessionLocal
    from .. import ai_runtime, jobs, live, notify, scheduling
    from .meetings import default_conn
    from .samples import template_for
    db = SessionLocal()
    try:
        conn = db.get(models.ZoomConnection, conn_id)
        org = db.get(models.Organization, conn.org_id) if conn else None
        if conn is None or org is None or not (org.settings or {}).get("zoom_auto_import"):
            return
        creator = db.get(models.User, conn.created_by)
        if creator is None:
            return
        client = zoom.Client(conn, db)
        rec = next((m for m in client.recordings(30) if m.get("uuid") == uuid), None)
        if rec is None:
            return
        mt = db.scalar(select(models.Meeting).where(models.Meeting.org_id == org.id, models.Meeting.zoom_recording_uuid == uuid))
        fresh = mt is None
        if not fresh and mt.zoom_text_source:
            return
        if fresh:
            when = None
            try:
                import datetime as dt
                when = dt.datetime.fromisoformat(str(rec.get("start_time", "")).replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass
            tpl = template_for(db, org, creator)
            mt = models.Meeting(org_id=org.id, title=(rec.get("topic") or "Zoom meeting")[:200],
                                meeting_date=scheduling.label_for(when, "America/Los_Angeles") if when else "", template_id=tpl.id,
                                ai_connection_id=default_conn(db, creator, org.id), run_mode="after", status="ended",
                                created_by=creator.id, draft={}, problems=[], snapshot_tail=[], scheduled_at=when,
                                visibility="private", duration_min=int(rec.get("duration") or 60) or 60,
                                zoom_recording_uuid=uuid)
            db.add(mt)
            db.flush()
        texts = client.texts(rec)
        counts = {}
        if texts.get("vtt"):
            counts["vtt"] = live.import_text(db, mt, texts["vtt"], "zoom.vtt")[1]
            mt.zoom_text_source = texts.get("source") or "transcript"
        if fresh and texts.get("chat"):
            counts["chat"] = live.import_text(db, mt, texts["chat"], "zoom.chat.txt")[1]
        if rec.get("share_url") and zoom.share_key(rec["share_url"]):
            mt.recording_link = rec["share_url"][:500]
        if not fresh and not counts:
            db.rollback()
            return
        audit.log(db, "zoom.auto_imported", None, org.id, "zoom", meeting=mt.id, event=event, **counts)
        db.commit()
        drafting = bool(counts.get("vtt")) and ai_runtime.resolve_connection(db, creator, org, "minutes")[0] is not None
        if drafting:
            jobs.enqueue(db, mt, "full")
            db.commit()
        body = ("Live Minutes imported the Zoom recording %s and %s." % (
            "with its " + ("closed captions" if mt.zoom_text_source == "captions" else "transcript") if counts.get("vtt") else "without a transcript yet",
            "started drafting the minutes" if drafting else "is waiting for you to draft the minutes"))
        notify.send(db, notify.members(db, org, "secretary"), "draft_ready", org, "Zoom recording imported: " + mt.title, body,
                    "/meetings/" + mt.id)
        db.commit()
    except Exception as exc:
        db.rollback()
        audit.log(db, "zoom.auto_import_failed", None, conn.org_id if conn else None, "zoom", error=str(exc)[:200])
        db.commit()
    finally:
        db.close()


@router.get("/api/orgs/{org_id}/zoom/checklist")
def checklist(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, org_id, "member")
    c = db.scalar(select(models.ZoomConnection).where(models.ZoomConnection.org_id == org_id))
    found, note = None, ""
    if c is not None:
        try:
            found = zoom.read_checks(zoom.Client(c, db).settings())
        except (ValueError, httpx.HTTPError):
            note = "Live Minutes could not read this Zoom account's settings. Disconnect and connect Zoom again to let it check."
    items = [{"key": k, "label": label, "why": why, "required": req, "where": where, "link": link,
              "ok": None if found is None else found.get(k)} for k, label, why, req, where, link in zoom.CHECKS]
    return {"checked": found is not None, "note": note, "items": items,
            "ready": found is not None and all(i["ok"] for i in items if i["required"])}


@router.get("/api/orgs/{org_id}/zoom/connect")
def connect(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, org_id, "secretary")
    if not zoom.configured():
        raise HTTPException(400, "the Zoom app is not configured on this server")
    state = secrets.token_urlsafe(24)
    resp = RedirectResponse(zoom.authorize_url(state), status_code=302)
    resp.set_cookie(scoped_cookie("lm_zoom"), encrypt(json.dumps({"s": state, "o": org_id, "u": user.id, "t": time.time()})),
                    httponly=True, samesite="lax", secure=settings.secure_cookies, max_age=600, path="/api/zoom")
    return resp


@router.get("/api/zoom/callback")
def callback(request: Request, code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    if not zoom.configured():
        raise HTTPException(400, "the Zoom app is not configured on this server")
    user = optional_user(request, db)
    raw = request.cookies.get(scoped_cookie("lm_zoom"), "")
    try:
        saved = json.loads(decrypt(raw)) if raw else None
    except (ValueError, json.JSONDecodeError):
        saved = None
    if error or not code:
        return forget(RedirectResponse("/settings?tab=zoom&zoom=denied" if saved else "/zoom/connect?zoom=denied",
                                       status_code=302), "lm_zoom")
    if state or saved:
        if (saved is None or user is None or saved.get("s") != state or saved.get("u") != user.id
                or time.time() - saved.get("t", 0) > 600):
            raise HTTPException(400, "Zoom connection expired; start again")
        org_id = saved["o"]
        require_role(db, user, org_id, "secretary")
        tok = zoom.exchange(code)
        save_connection(db, request, user, org_id, tok, zoom.identity(tok["access_token"]))
        db.commit()
        return forget(RedirectResponse("/settings?tab=zoom&zoom=connected", status_code=302), "lm_zoom")
    ratelimit.hit("zoom-install:" + client_ip(request), 30, 3600, "too many Zoom connections from your network; try again later")
    purge_pending(db)
    tok = zoom.exchange(code)
    who = zoom.identity(tok["access_token"])
    row = models.ZoomPending(token_enc=encrypt(json.dumps(tok)), host_email=who["email"], zoom_user_id=who["id"],
                             zoom_account_id=who["account_id"], expires_at=time.time() + PENDING_SECONDS)
    db.add(row)
    db.commit()
    resp = RedirectResponse("/zoom/connect", status_code=302)
    resp.set_cookie(scoped_cookie("lm_zoom_pending"), encrypt(row.id), **cookie_opts(PENDING_SECONDS))
    return resp


@router.get("/api/zoom/pending")
def pending(request: Request, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    row = pending_row(request, db)
    return {"host_email": row.host_email, "expires_at": row.expires_at,
            "workspaces": [{"id": o.id, "name": o.name} for o in eligible(db, user)]}


@router.post("/api/zoom/pending/claim")
def claim(body: ClaimIn, request: Request, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    row = pending_row(request, db)
    require_role(db, user, body.org_id, "secretary")
    tok = json.loads(decrypt(row.token_enc))
    save_connection(db, request, user, body.org_id, tok,
                    {"email": row.host_email, "id": row.zoom_user_id, "account_id": row.zoom_account_id})
    db.delete(row)
    db.commit()
    return forget(JSONResponse({"ok": True, "org_id": body.org_id}), "lm_zoom_pending")


@router.delete("/api/zoom/pending")
def discard(request: Request, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    row = pending_row(request, db)
    try:
        zoom.revoke_token(json.loads(decrypt(row.token_enc)).get("access_token", ""))
    except (ValueError, json.JSONDecodeError):
        pass
    db.delete(row)
    audit.log(db, "zoom.discarded", user, None, client_ip(request), host=row.host_email)
    db.commit()
    return forget(JSONResponse({"ok": True}), "lm_zoom_pending")


@router.delete("/api/orgs/{org_id}/zoom")
def disconnect(org_id: str, request: Request, user: models.User = Depends(current_user),
               db: Session = Depends(get_db)):
    require_role(db, user, org_id, "secretary")
    c = connection(db, org_id)
    try:
        revoked = zoom.Client(c, db).revoke()
    except (ValueError, KeyError, json.JSONDecodeError):
        revoked = False
    db.delete(c)
    audit.log(db, "zoom.disconnected", user, org_id, client_ip(request), revoked=revoked)
    db.commit()
    return {"ok": True, "revoked": revoked}


@router.post("/api/zoom/events")
async def events(request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    if not settings.zoom_secret_token:
        raise HTTPException(404, "not found")
    body = await request.body()
    if not zoom.signature_ok(request.headers.get("x-zm-request-timestamp", ""), body,
                             request.headers.get("x-zm-signature", "")):
        raise HTTPException(401, "bad signature")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "bad event")
    event = data.get("event", "")
    payload = data.get("payload") or {}
    if event == "endpoint.url_validation":
        plain = str(payload.get("plainToken", ""))[:200]
        return {"plainToken": plain, "encryptedToken": zoom.sign(plain.encode())}
    if event == "app_deauthorized" and payload.get("user_id"):
        zoom_user = str(payload["user_id"])[:64]
        rows = db.scalars(select(models.ZoomConnection).where(models.ZoomConnection.zoom_user_id == zoom_user)).all()
        for c in rows:
            audit.log(db, "zoom.deauthorized", None, c.org_id, client_ip(request), host=c.host_email)
            db.delete(c)
        db.execute(delete(models.ZoomPending).where(models.ZoomPending.zoom_user_id == zoom_user))
        db.commit()
    if event in AUTO_EVENTS:
        obj = payload.get("object") or {}
        uuid, host = str(obj.get("uuid") or "")[:200], str(obj.get("host_id") or "")[:64]
        if uuid and host:
            for c in db.scalars(select(models.ZoomConnection).where(models.ZoomConnection.zoom_user_id == host)).all():
                org = db.get(models.Organization, c.org_id)
                if org is not None and (org.settings or {}).get("zoom_auto_import"):
                    background.add_task(auto_import, c.id, uuid, event)
    return Response(status_code=204)


@router.get("/api/orgs/{org_id}/zoom/recordings")
def recordings(org_id: str, days: int = 30, user: models.User = Depends(current_user),
               db: Session = Depends(get_db)):
    require_role(db, user, org_id, "secretary")
    try:
        rows = zoom.Client(connection(db, org_id), db).recordings(days)
    except ValueError as exc:
        raise HTTPException(502, str(exc))
    return {"recordings": [{"uuid": m.get("uuid"), "id": m.get("id"), "topic": m.get("topic"),
                            "start_time": m.get("start_time"),
                            "files": sorted({f.get("file_type") for f in m.get("recording_files", [])})}
                           for m in rows]}


@router.post("/api/meetings/{meeting_id}/zoom-import")
def zoom_import(meeting_id: str, body: ZoomImportIn, request: Request, user: models.User = Depends(current_user),
                db: Session = Depends(get_db)):
    mt, _, _ = meeting_for(db, user, meeting_id, "secretary")
    client = zoom.Client(connection(db, mt.org_id), db)
    from .recordings import import_zoom
    try:
        rec = next((m for m in client.recordings(30) if m.get("uuid") == body.uuid), None)
        if rec is None:
            raise HTTPException(404, "recording not found in the last 30 days")
        counts = import_zoom(db, mt, client, rec, body.recording)
    except ValueError as exc:
        raise HTTPException(502, str(exc))
    audit.log(db, "zoom.imported", user, mt.org_id, client_ip(request), meeting=mt.id, **counts)
    db.commit()
    return {"transcript_lines": counts.get("vtt", 0), "chat_lines": counts.get("chat", 0), "recording": bool(counts.get("recording")),
            "source": counts.get("source", ""), "recording_skipped": counts.get("recording_skipped", "")}
