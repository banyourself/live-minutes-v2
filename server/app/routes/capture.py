import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import audit, jobs, live, models, officers, ratelimit, runtime
from ..db import get_db
from ..deps import client_ip, current_user, require_role
from ..security import new_token, token_hash

router = APIRouter(tags=["capture"])
MAX_SNAPSHOT = 200_000
SOON = 30 * 60
LATE = 4 * 3600


class TokenIn(BaseModel):
    label: str = ""


class CaptureIn(BaseModel):
    snapshot: str = ""
    lines: list[dict] = []


def token_org(request, db):
    raw = request.headers.get("X-Capture-Token", "")
    auth = request.headers.get("Authorization", "")
    if not raw and auth.startswith("Capture "):
        raw = auth[8:]
    if not raw:
        raise HTTPException(401, "missing capture token")
    ip_key = "capture-bad:" + client_ip(request)
    if ratelimit.blocked(ip_key, 30, 600):
        raise HTTPException(429, "too many invalid capture tokens; wait a few minutes")
    tok = db.scalar(select(models.CaptureToken).where(models.CaptureToken.token_hash == token_hash(raw)))
    if tok is None or tok.revoked or (tok.expires_at and tok.expires_at < time.time()):
        ratelimit.record(ip_key)
        raise HTTPException(401, "this capture token is not valid or has expired; create a new one in Settings")
    owner = db.get(models.User, tok.user_id)
    m = db.scalar(select(models.Membership).where(models.Membership.user_id == tok.user_id,
                                                  models.Membership.org_id == tok.org_id))
    if owner is None or owner.disabled or m is None or models.ROLE_RANK[officers.effective_role(db, m)] < models.ROLE_RANK["member"]:
        raise HTTPException(403, "the owner of this token no longer has access")
    if runtime.get("maintenance_mode"):
        raise HTTPException(503, "Live Minutes is down for maintenance; try again soon")
    tok.last_used_at = time.time()
    return tok


@router.get("/api/orgs/{org_id}/capture-tokens")
def list_tokens(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, org_id, "member")
    rows = db.scalars(select(models.CaptureToken).where(models.CaptureToken.org_id == org_id,
                                                        models.CaptureToken.user_id == user.id,
                                                        models.CaptureToken.revoked.is_(False))).all()
    return {"tokens": [{"id": t.id, "label": t.label, "created_at": t.created_at, "last_used_at": t.last_used_at,
                        "expires_at": t.expires_at} for t in rows]}


@router.post("/api/orgs/{org_id}/capture-tokens")
def create_token(org_id: str, body: TokenIn, request: Request, user: models.User = Depends(current_user),
                 db: Session = Depends(get_db)):
    require_role(db, user, org_id, "member")
    raw = "lmc_" + new_token()
    db.add(models.CaptureToken(user_id=user.id, org_id=org_id, token_hash=token_hash(raw),
                               label=(body.label or "Capture device")[:120],
                               expires_at=time.time() + int(runtime.get("capture_token_days")) * 86400))
    audit.log(db, "capture_token.created", user, org_id, client_ip(request), label=body.label)
    db.commit()
    return {"token": raw}


@router.delete("/api/orgs/{org_id}/capture-tokens/{token_id}")
def revoke_token(org_id: str, token_id: str, request: Request, user: models.User = Depends(current_user),
                 db: Session = Depends(get_db)):
    require_role(db, user, org_id, "member")
    t = db.get(models.CaptureToken, token_id)
    if t is None or t.org_id != org_id or t.user_id != user.id:
        raise HTTPException(404, "token not found")
    t.revoked = True
    audit.log(db, "capture_token.revoked", user, org_id, client_ip(request), token=t.id)
    db.commit()
    return {"ok": True}


@router.get("/api/capture/meetings")
def capture_meetings(request: Request, db: Session = Depends(get_db)):
    tok = token_org(request, db)
    org = db.get(models.Organization, tok.org_id)
    now = time.time()
    rows = db.scalars(select(models.Meeting).where(models.Meeting.org_id == tok.org_id,
                                                   models.Meeting.sample.is_(False),
                                                   or_(models.Meeting.status == "open",
                                                       (models.Meeting.status == "scheduled")
                                                       & (models.Meeting.scheduled_at < now + SOON)
                                                       & (models.Meeting.scheduled_at > now - LATE)))
                      .order_by(models.Meeting.created_at.desc()).limit(20)).all()
    db.commit()
    return {"organization": org.name, "meetings": [{"id": m.id, "title": m.title, "meeting_date": m.meeting_date}
                                                   for m in rows]}


@router.post("/api/capture/meetings/{meeting_id}")
def capture(meeting_id: str, body: CaptureIn, request: Request, db: Session = Depends(get_db)):
    tok = token_org(request, db)
    mt = db.get(models.Meeting, meeting_id)
    if mt is None or mt.org_id != tok.org_id:
        raise HTTPException(404, "meeting not found")
    if mt.status == "scheduled" and mt.scheduled_at and time.time() - LATE < mt.scheduled_at < time.time() + SOON:
        mt.status = "open"
        audit.log(db, "meeting.started", None, mt.org_id, client_ip(request), meeting=mt.id, by="capture")
    if mt.status != "open":
        raise HTTPException(409, "this meeting is not open; captions are only accepted during the meeting")
    if len(body.snapshot) > MAX_SNAPSHOT or len(body.lines) > 500:
        raise HTTPException(413, "caption update is too large")
    added = 0
    if body.snapshot:
        added += live.ingest_snapshot(db, mt, body.snapshot)
    if body.lines:
        added += live.ingest_lines(db, mt, body.lines)
    db.flush()
    job = jobs.maybe_enqueue_live(db, mt)
    db.commit()
    return {"ok": True, "added": added, "drafting": bool(job)}
