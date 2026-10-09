import csv
import io
import os
import re
import shutil
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, governance, live, media, models, personal, ratelimit, records, scheduling, scope, storage, zoom
from ..db import get_db
from ..deps import client_ip, current_user, meeting_for, require_role, sudo_user
from ..settings import settings
from .meetings import download_name, meeting_payload
from .zoom import connection

router = APIRouter(tags=["recordings"])


class StartIn(BaseModel):
    name: str = ""
    size: int


class LinkIn(BaseModel):
    url: str = ""


class ZoomLinkIn(BaseModel):
    share_url: str
    title: str = ""
    template_id: str
    recording: bool = True
    notice_ack: bool = False


def clean_link(url):
    url = scheduling.clean_zoom_url(url)
    if url and not zoom.share_key(url):
        raise HTTPException(400, "paste the Zoom recording share link, like https://college.zoom.us/rec/share/...")
    return url


def attach(db, mt, info):
    old = mt.recording_key
    if old:
        governance.check_hold(db, db.get(models.Organization, mt.org_id), "replace this recording")
    mt.recording_key, mt.recording_type, mt.recording_size, mt.recording_name = info["key"], info["type"], info["size"], info["name"]
    if old and old != info["key"]:
        storage.store().delete(old)
    mt.updated_at = time.time()


@router.post("/api/meetings/{meeting_id}/recording/uploads")
def start_upload(meeting_id: str, body: StartIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    mt, org, _ = meeting_for(db, user, meeting_id, "secretary")
    if mt.recording_key:
        governance.check_hold(db, org, "replace this recording")
    personal.check_room(db, org.id, body.size, mt.id)
    return {"upload_id": media.start(mt.id, user.id, body.name, body.size, mt.org_id), "chunk_size": media.CHUNK}


@router.put("/api/meetings/{meeting_id}/recording/uploads/{upload_id}/{index}")
async def upload_part(meeting_id: str, upload_id: str, index: int, request: Request,
                      user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    meeting_for(db, user, meeting_id, "secretary")
    db.close()
    return {"received": await media.write_part(request, upload_id, meeting_id, index)}


@router.post("/api/meetings/{meeting_id}/recording/uploads/{upload_id}/finish")
def finish_upload(meeting_id: str, upload_id: str, request: Request, user: models.User = Depends(current_user),
                  db: Session = Depends(get_db)):
    mt, _, role = meeting_for(db, user, meeting_id, "secretary")
    info = media.assemble(upload_id, mt.id, mt.org_id)
    if not personal.has_room(db, mt.org_id, info["size"], mt.id):
        storage.store().delete(info["key"])
        personal.check_room(db, mt.org_id, info["size"], mt.id)
    attach(db, mt, info)
    audit.log(db, "meeting.recording_uploaded", user, mt.org_id, client_ip(request), meeting=mt.id, size=info["size"],
              type=info["type"])
    db.commit()
    return meeting_payload(db, mt, role, user)


@router.delete("/api/meetings/{meeting_id}/recording")
def delete_recording(meeting_id: str, request: Request, user: models.User = Depends(current_user),
                     db: Session = Depends(get_db)):
    mt, org, role = meeting_for(db, user, meeting_id, "secretary")
    governance.check_hold(db, org, "delete this recording")
    if mt.recording_key:
        storage.store().delete(mt.recording_key)
        audit.log(db, "meeting.recording_deleted", user, mt.org_id, client_ip(request), meeting=mt.id)
    mt.recording_key, mt.recording_type, mt.recording_size, mt.recording_name = "", "", 0, ""
    db.commit()
    return meeting_payload(db, mt, role, user)


@router.put("/api/meetings/{meeting_id}/recording-link")
def set_link(meeting_id: str, body: LinkIn, request: Request, user: models.User = Depends(current_user),
             db: Session = Depends(get_db)):
    mt, _, role = meeting_for(db, user, meeting_id, "secretary")
    mt.recording_link = clean_link(body.url)
    audit.log(db, "meeting.recording_link", user, mt.org_id, client_ip(request), meeting=mt.id)
    db.commit()
    return meeting_payload(db, mt, role, user)


@router.get("/api/meetings/{meeting_id}/recording")
def play(meeting_id: str, request: Request, download: int = 0, user: models.User = Depends(current_user),
         db: Session = Depends(get_db)):
    mt, _, _ = meeting_for(db, user, meeting_id, "viewer")
    if not mt.recording_key:
        raise HTTPException(404, "this meeting has no recording")
    name = download_name(mt, media.EXT.get(mt.recording_type, "bin"))
    db.close()
    return media.stream(request, mt.recording_key, mt.recording_type, name, bool(download))


def with_recordings(db, org_ids):
    return db.scalars(select(models.Meeting).where(models.Meeting.org_id.in_(list(org_ids) or [""]),
                                                   models.Meeting.recording_key.is_not(None),
                                                   models.Meeting.recording_key != "")
                      .order_by(models.Meeting.created_at.desc())).all()


def recording_row(m):
    return {"id": m.id, "title": m.title, "meeting_date": m.meeting_date, "status": m.status,
            "type": m.recording_type, "size": m.recording_size or 0, "created_at": m.created_at}


def part(text, fallback):
    return re.sub(r"[^\w\- .,()&]+", "", text or "").strip(" .")[:80] or fallback


def zip_of(db, meetings, orgs, filename, folders=False):
    names, entries = set(), []
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["file", "organization", "meeting", "date", "status", "bytes", "link"])
    for m in meetings:
        folder = part(orgs[m.org_id].name, "organization") if folders else ""
        stem = part(((m.meeting_date or time.strftime("%Y-%m-%d", time.gmtime(m.created_at))) + " " + m.title), m.id)
        ext = media.EXT.get(m.recording_type, "bin")
        name = (folder + "/" if folder else "") + stem + "." + ext
        n = 2
        while name.lower() in names:
            name = (folder + "/" if folder else "") + "%s (%d).%s" % (stem, n, ext)
            n += 1
        names.add(name.lower())
        try:
            size = storage.store().size(m.recording_key)
        except Exception:
            continue
        entries.append((name, m.recording_key, size))
        w.writerow([records.safe_cell(v) for v in (name, orgs[m.org_id].name, m.title, m.meeting_date, m.status, size,
                                                   settings.public_url + "/meetings/" + m.id)])
    db.close()
    return StreamingResponse(media.zip_stream(entries, [("recordings.csv", out.getvalue().encode("utf-8-sig"))]),
                             media_type="application/zip",
                             headers={"Content-Disposition": 'attachment; filename="%s"' % filename,
                                      "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


def zip_name(label):
    return "%s-recordings-%s.zip" % (governance.slug(label, "live-minutes"), time.strftime("%Y-%m-%d"))


@router.get("/api/orgs/{org_id}/recordings")
def org_recordings(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    org, role = require_role(db, user, org_id, "viewer")
    rows = with_recordings(db, [org.id])
    return {"recordings": [recording_row(m) for m in rows], "total_bytes": sum(m.recording_size or 0 for m in rows),
            "can_download_all": models.ROLE_RANK[role] >= models.ROLE_RANK["secretary"]}


@router.get("/api/orgs/{org_id}/recordings.zip")
def org_recordings_zip(org_id: str, request: Request, user: models.User = Depends(current_user),
                       db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "secretary")
    ratelimit.hit("rec-zip:" + user.id, 6, 3600, "you have downloaded a lot of recordings; try again in an hour")
    rows = with_recordings(db, [org.id])
    if not rows:
        raise HTTPException(404, "this organization has no recordings")
    audit.log(db, "recordings.downloaded", user, org.id, client_ip(request), count=len(rows))
    db.commit()
    return zip_of(db, rows, {org.id: org}, zip_name(org.name))


def scope_orgs(db, user, scope_name, target_id):
    ctx = scope.resolve(db, user, scope_name, target_id)
    orgs = {o.id: o for o in scope.orgs_in(db, ctx)}
    return ctx, orgs


@router.get("/api/manage/{scope_name}/{target_id}/recordings")
def scope_recordings(scope_name: str, target_id: str, user: models.User = Depends(current_user),
                     db: Session = Depends(get_db)):
    _, orgs = scope_orgs(db, user, scope_name, target_id)
    rows = with_recordings(db, orgs)
    return {"count": len(rows), "total_bytes": sum(m.recording_size or 0 for m in rows),
            "organizations": len({m.org_id for m in rows})}


@router.get("/api/manage/{scope_name}/{target_id}/recordings.zip")
def scope_recordings_zip(scope_name: str, target_id: str, request: Request, check: int = 0,
                         user: models.User = Depends(sudo_user), db: Session = Depends(get_db)):
    ctx, orgs = scope_orgs(db, user, scope_name, target_id)
    rows = with_recordings(db, orgs)
    if not rows:
        raise HTTPException(404, "there are no recordings here")
    if check:
        return {"ready": True, "count": len(rows)}
    ratelimit.hit("rec-zip:" + user.id, 6, 3600, "you have downloaded a lot of recordings; try again in an hour")
    label = ctx["district"].name if ctx["scope"] == "district" else ctx["school"].name
    audit.log(db, "recordings.downloaded", user, ip=client_ip(request), scope=ctx["scope"], target=target_id, count=len(rows))
    db.commit()
    return zip_of(db, rows, orgs, zip_name(label), folders=True)


def import_zoom(db, mt, client, rec, with_recording):
    texts = client.texts(rec)
    counts = {"source": texts.get("source", "")} if texts.get("source") else {}
    for kind in ("vtt", "chat"):
        if texts[kind]:
            counts[kind] = live.import_text(db, mt, texts[kind], "zoom." + ("vtt" if kind == "vtt" else "chat.txt"))[1]
    if with_recording:
        files = rec.get("recording_files", [])
        pick = next((f for f in files if f.get("file_type") == "MP4" and f.get("recording_type") == "shared_screen_with_speaker_view"), None) \
            or next((f for f in files if f.get("file_type") == "MP4"), None) \
            or next((f for f in files if f.get("file_type") == "M4A"), None)
        if pick and pick.get("download_url"):
            work = storage.workdir()
            try:
                path = os.path.join(work, "zoom." + pick["file_type"].lower())
                client.download(pick["download_url"], path, media.max_bytes())
                if personal.has_room(db, mt.org_id, os.path.getsize(path), mt.id):
                    attach(db, mt, media.store_file(path, mt.org_id, mt.id, (rec.get("topic") or "recording") + "." + pick["file_type"].lower()))
                    counts["recording"] = 1
                else:
                    counts["recording_skipped"] = "storage"
            finally:
                shutil.rmtree(work, ignore_errors=True)
    if rec.get("share_url"):
        mt.recording_link = rec["share_url"][:500] if zoom.share_key(rec["share_url"]) else mt.recording_link
    return counts


@router.post("/api/orgs/{org_id}/zoom/import-link")
def import_link(org_id: str, body: ZoomLinkIn, request: Request, user: models.User = Depends(current_user),
                db: Session = Depends(get_db)):
    org, role = require_role(db, user, org_id, "secretary")
    link = clean_link(body.share_url)
    if not link:
        raise HTTPException(400, "paste the Zoom recording share link")
    tpl = db.get(models.Template, body.template_id)
    if tpl is None or tpl.org_id != org_id or tpl.purpose != "template":
        raise HTTPException(400, "choose a template from this organization")
    try:
        conn = connection(db, org_id)
    except HTTPException:
        raise HTTPException(400, "connect the Zoom account that hosts this meeting under Settings, Zoom first, or download "
                                 "the files from the share page and upload them")
    client = zoom.Client(conn, db)
    try:
        rec = client.find_share(link)
    except ValueError as exc:
        raise HTTPException(502, str(exc))
    if rec is None:
        raise HTTPException(404, "the connected Zoom account has no recording with this link in the last 6 months")
    when = None
    try:
        import datetime as dt
        when = dt.datetime.fromisoformat(rec.get("start_time", "").replace("Z", "+00:00")).timestamp()
    except ValueError:
        pass
    mt = models.Meeting(org_id=org_id, title=(body.title or rec.get("topic") or "Zoom meeting")[:200],
                        meeting_date=scheduling.label_for(when, "America/Los_Angeles") if when else "", template_id=tpl.id,
                        run_mode="after", status="ended", created_by=user.id, draft={}, problems=[], snapshot_tail=[],
                        scheduled_at=when, visibility="private",
                        duration_min=int(rec.get("duration") or 60) or 60)
    db.add(mt)
    db.flush()
    try:
        counts = import_zoom(db, mt, client, rec, body.recording)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(502, str(exc))
    audit.log(db, "zoom.imported_link", user, org_id, client_ip(request), meeting=mt.id, notice_ack=body.notice_ack, **counts)
    db.commit()
    return meeting_payload(db, mt, role, user)
