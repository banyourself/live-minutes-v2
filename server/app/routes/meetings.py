import os
import re
import shutil
import time
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from minutes_app import accessibility, drafter, motions

from .. import ai_runtime, audit, free_ai, governance, history, jobs, live, models, notify, officers, scheduling, storage
from ..db import get_db
from ..deps import client_ip, current_user, meeting_for, require_role

router = APIRouter(tags=["meetings"])
_motion_cache = {}


class MeetingIn(BaseModel):
    title: str
    meeting_date: str = ""
    template_id: str
    ai_connection_id: str | None = None
    run_mode: str = "live"
    notes: str = ""
    scheduled_at: float | None = None
    duration_min: int = 60
    timezone: str = ""
    zoom_url: str = ""
    location: str = ""
    status: str = ""
    notice_ack: bool = False


class MeetingPatch(BaseModel):
    title: str | None = None
    meeting_date: str | None = None
    notes: str | None = None
    run_mode: str | None = None
    ai_connection_id: str | None = None
    draft: dict | None = None
    base_rev: int | None = None
    scheduled_at: float | None = None
    duration_min: int | None = None
    zoom_url: str | None = None
    location: str | None = None


class ImportIn(BaseModel):
    filename: str = ""
    text: str


def review_payload(db, mt, user):
    org = db.get(models.Organization, mt.org_id)
    who = db.get(models.User, mt.reviewed_by) if mt.reviewed_by else None
    return {"status": mt.review_status or "", "note": mt.review_note or "", "requested_at": mt.review_requested_at,
            "reviewed_at": mt.reviewed_at, "reviewer": (who.name or who.email) if who else "",
            "required": officers.review_required(db, org),
            "has_reviewers": bool(officers.holders_with(db, org.id, "review_minutes")),
            "can_review": officers.authority(db, user, org).has("review_minutes")}


def free_progress(db, mt):
    return free_ai.minutes_progress(db, mt.id) or free_ai.queued_minutes(db, mt.id, live.line_count(db, mt.id))


def meeting_payload(db, mt, role, user):
    tpl = db.get(models.Template, mt.template_id)
    conn = db.get(models.AIConnection, mt.ai_connection_id) if mt.ai_connection_id else None
    return {"id": mt.id, "org_id": mt.org_id, "title": mt.title, "meeting_date": mt.meeting_date,
            "status": mt.status, "run_mode": mt.run_mode, "notes": mt.notes, "role": role,
            "template": {"id": tpl.id, "name": tpl.name, "mode": tpl.mode} if tpl else None,
            "ai_connection": {"id": conn.id, "label": conn.label, "model": conn.model, "free": ai_runtime.is_free(conn)} if conn else None,
            "free_ai": free_progress(db, mt) if ai_runtime.is_free(conn) and mt.draft_status in ("queued", "drafting") else None,
            "draft": mt.draft or {}, "draft_rev": mt.draft_rev or 0, "problems": mt.problems or [],
            "draft_status": mt.draft_status,
            "draft_error": mt.draft_error, "drafted_upto": mt.drafted_upto,
            "line_count": live.line_count(db, mt.id), "updated_at": mt.updated_at,
            "approved_at": mt.approved_at, "has_export": bool(mt.export_key), "created_at": mt.created_at,
            "scheduled_at": mt.scheduled_at, "duration_min": mt.duration_min, "timezone": mt.timezone,
            "zoom_url": mt.zoom_url, "location": mt.location, "series_id": mt.series_id, "sample": mt.sample,
            "recording": {"type": mt.recording_type, "size": mt.recording_size, "name": mt.recording_name}
            if mt.recording_key else None, "recording_link": mt.recording_link,
            "review": review_payload(db, mt, user)}


def check_when(when, duration):
    if not 5 <= duration <= 600:
        raise HTTPException(400, "meetings can last 5 minutes to 10 hours")
    if when is None:
        return None
    if not time.time() - 86400 * 366 < when < time.time() + 86400 * 731:
        raise HTTPException(400, "schedule the meeting within the next two years")
    return float(int(when))


def default_conn(db, user, org_id):
    conn, _ = ai_runtime.resolve_connection(db, user, db.get(models.Organization, org_id), "minutes")
    return conn.id if conn is not None else None


def check_conn(db, org_id, conn_id, user=None):
    if not conn_id:
        return None
    org = db.get(models.Organization, org_id)
    if conn_id not in {c.id for c in ai_runtime.available(db, user, org)}:
        raise HTTPException(400, "choose an AI that is available to this organization")
    return conn_id


@router.get("/api/orgs/{org_id}/meetings")
def list_meetings(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, org_id, "viewer")
    rows = db.scalars(select(models.Meeting).where(models.Meeting.org_id == org_id,
                                                   or_(models.Meeting.status != "scheduled",
                                                       models.Meeting.scheduled_at <= time.time()))
                      .order_by(models.Meeting.created_at.desc()).limit(200)).all()
    return {"meetings": [{"id": m.id, "title": m.title, "meeting_date": m.meeting_date, "status": m.status,
                          "run_mode": m.run_mode, "created_at": m.created_at, "approved_at": m.approved_at,
                          "scheduled_at": m.scheduled_at, "zoom_url": m.zoom_url, "series_id": m.series_id,
                          "has_recording": bool(m.recording_key), "sample": m.sample}
                         for m in rows]}


UNRESOLVED_DAYS = 180


@router.get("/api/orgs/{org_id}/unresolved")
def unresolved(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, org_id, "secretary")
    rows = db.execute(
        select(models.MotionRecord, models.Meeting)
        .join(models.Meeting, models.Meeting.id == models.MotionRecord.meeting_id)
        .where(models.MotionRecord.org_id == org_id, models.MotionRecord.result.in_(("tabled", "")),
               models.Meeting.org_id == org_id, models.Meeting.status.in_(("ended", "approved")),
               models.Meeting.sample.is_(False), models.Meeting.created_at >= time.time() - UNRESOLVED_DAYS * 86400)
        .order_by(models.Meeting.created_at.desc(), models.MotionRecord.position)
        .limit(30)).all()
    return {"items": [{"id": m.id, "text": m.text[:500], "under": m.under[:300], "result": m.result or "no_result",
                       "mover": m.mover[:200], "meeting_id": mt.id, "meeting_title": mt.title, "meeting_date": mt.meeting_date}
                      for m, mt in rows]}


@router.post("/api/orgs/{org_id}/meetings")
def create_meeting(org_id: str, body: MeetingIn, request: Request, user: models.User = Depends(current_user),
                   db: Session = Depends(get_db)):
    _, role = require_role(db, user, org_id, "secretary")
    tpl = db.get(models.Template, body.template_id)
    if tpl is None or tpl.org_id != org_id:
        raise HTTPException(400, "choose a template from this organization")
    if tpl.purpose != "template":
        raise HTTPException(400, "an example is used for style; choose a template to fill in")
    if body.run_mode not in ("live", "after"):
        raise HTTPException(400, "mode must be live or after")
    when = check_when(body.scheduled_at, body.duration_min)
    tz = scheduling.clean_tz(body.timezone) if body.timezone else ("UTC" if when else "")
    label = body.meeting_date[:80] or (scheduling.label_for(when, tz) if when else "")
    mt = models.Meeting(org_id=org_id, title=body.title.strip()[:200] or "Meeting", meeting_date=label,
                        template_id=tpl.id,
                        ai_connection_id=check_conn(db, org_id, body.ai_connection_id, user) or default_conn(db, user, org_id),
                        run_mode=body.run_mode, notes=body.notes[:6000], created_by=user.id, draft={}, problems=[],
                        snapshot_tail=[], scheduled_at=when, duration_min=body.duration_min, timezone=tz,
                        zoom_url=scheduling.clean_zoom_url(body.zoom_url),
                        location=" ".join(body.location.split())[:200],
                        status="ended" if body.status == "ended" else "scheduled" if when and when > time.time() + 300 else "open",
                        visibility="private")
    db.add(mt)
    audit.log(db, "meeting.created", user, org_id, client_ip(request), meeting=mt.id, title=mt.title, notice_ack=body.notice_ack)
    db.commit()
    return meeting_payload(db, mt, role, user)


@router.get("/api/meetings/{meeting_id}")
def get_meeting(meeting_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    mt, _, role = meeting_for(db, user, meeting_id)
    return meeting_payload(db, mt, role, user)


def motions_for(db, mt):
    key = mt.id
    cached = _motion_cache.get(key)
    if cached and cached[0] == mt.updated_at:
        return cached[1]
    tr, _ = live.transcript_for(db, mt.id)
    result = motions.track(tr.lines)
    for m in result:
        m.pop("confirmed", None)
    _motion_cache[key] = (mt.updated_at, result)
    if len(_motion_cache) > 500:
        _motion_cache.clear()
    return result


@router.get("/api/meetings/{meeting_id}/live")
def live_state(meeting_id: str, after_seq: int = 0, since: float = 0.0, user: models.User = Depends(current_user),
               db: Session = Depends(get_db)):
    mt, _, role = meeting_for(db, user, meeting_id)
    rows = db.scalars(select(models.TranscriptLine).where(
        models.TranscriptLine.meeting_id == mt.id,
        or_(models.TranscriptLine.seq >= after_seq, models.TranscriptLine.updated_at > since))
        .order_by(models.TranscriptLine.seq).limit(2000)).all()
    return {"server_time": time.time(), "meeting": meeting_payload(db, mt, role, user),
            "lines": [{"seq": r.seq, "t": r.t, "speaker": r.speaker, "text": r.text, "source": r.source}
                      for r in rows],
            "motions": motions_for(db, mt)}


@router.patch("/api/meetings/{meeting_id}")
def patch_meeting(meeting_id: str, body: MeetingPatch, request: Request, user: models.User = Depends(current_user),
                  db: Session = Depends(get_db)):
    mt, _, role = meeting_for(db, user, meeting_id, "secretary")
    if mt.status == "approved" and body.draft is not None:
        raise HTTPException(400, "these minutes are approved; reopen them before editing")
    if body.draft is not None and body.base_rev is not None and body.base_rev != (mt.draft_rev or 0):
        raise HTTPException(409, "the draft changed since you opened it; review the latest version and save again")
    if body.title is not None:
        mt.title = body.title.strip()[:200] or mt.title
    if body.meeting_date is not None:
        mt.meeting_date = body.meeting_date[:80]
    if body.notes is not None:
        mt.notes = body.notes[:6000]
    if body.run_mode is not None:
        if body.run_mode not in ("live", "after"):
            raise HTTPException(400, "mode must be live or after")
        mt.run_mode = body.run_mode
    if body.ai_connection_id is not None:
        mt.ai_connection_id = check_conn(db, mt.org_id, body.ai_connection_id, user)
    if body.zoom_url is not None:
        mt.zoom_url = scheduling.clean_zoom_url(body.zoom_url)
    if body.location is not None:
        mt.location = " ".join(body.location.split())[:200]
    if body.duration_min is not None:
        check_when(None, body.duration_min)
        mt.duration_min = body.duration_min
    if body.scheduled_at is not None:
        if mt.status != "scheduled":
            raise HTTPException(400, "this meeting has already started")
        mt.scheduled_at = check_when(body.scheduled_at, mt.duration_min or 60)
        if body.meeting_date is None:
            mt.meeting_date = scheduling.label_for(mt.scheduled_at, mt.timezone or "UTC")
    if body.draft is not None:
        tpl = db.get(models.Template, mt.template_id)
        work = storage.workdir()
        try:
            mt.problems = drafter.check(storage.store().local_copy(tpl.storage_key, work), body.draft)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        before = mt.draft or {}
        mt.draft = body.draft
        mt.draft_rev = (mt.draft_rev or 0) + 1
        history.record(db, mt, before, "person", user)
        if mt.review_status == "reviewed":
            mt.review_status, mt.review_note = "", "Edited after review; send it for review again."
        audit.log(db, "meeting.draft_edited", user, mt.org_id, client_ip(request), meeting=mt.id)
    mt.updated_at = time.time()
    db.commit()
    return meeting_payload(db, mt, role, user)


@router.post("/api/meetings/{meeting_id}/import")
def import_transcript(meeting_id: str, body: ImportIn, request: Request, user: models.User = Depends(current_user),
                      db: Session = Depends(get_db)):
    mt, _, _ = meeting_for(db, user, meeting_id, "secretary")
    if len(body.text) > 5_000_000:
        raise HTTPException(413, "transcript is too large")
    kind, n = live.import_text(db, mt, body.text, body.filename)
    audit.log(db, "meeting.imported", user, mt.org_id, client_ip(request), meeting=mt.id, kind=kind, lines=n)
    db.commit()
    return {"kind": kind, "lines": n}


@router.post("/api/meetings/{meeting_id}/draft")
def request_draft(meeting_id: str, body: dict | None = None, user: models.User = Depends(current_user),
                  db: Session = Depends(get_db)):
    mt, _, _ = meeting_for(db, user, meeting_id, "secretary")
    if mt.status == "approved":
        raise HTTPException(400, "these minutes are approved; reopen them before drafting again")
    if not mt.ai_connection_id:
        conn, _ = ai_runtime.resolve_connection(db, user, db.get(models.Organization, mt.org_id), "minutes")
        if conn is None:
            raise HTTPException(400, "no AI is set up for drafting minutes; add one under Settings, AI")
        mt.ai_connection_id = conn.id
    job = jobs.enqueue(db, mt, "full" if (body or {}).get("full") else "update")
    db.commit()
    return {"job": job.id, "status": job.status}


@router.post("/api/meetings/{meeting_id}/end")
def end_meeting(meeting_id: str, request: Request, user: models.User = Depends(current_user),
                db: Session = Depends(get_db)):
    mt, _, role = meeting_for(db, user, meeting_id, "secretary")
    if mt.status == "open":
        mt.status = "ended"
        if mt.ai_connection_id:
            jobs.enqueue(db, mt, "full")
    mt.updated_at = time.time()
    audit.log(db, "meeting.ended", user, mt.org_id, client_ip(request), meeting=mt.id)
    db.commit()
    return meeting_payload(db, mt, role, user)


@router.post("/api/meetings/{meeting_id}/approve")
def approve(meeting_id: str, request: Request, user: models.User = Depends(current_user),
            db: Session = Depends(get_db)):
    mt, org, role = meeting_for(db, user, meeting_id, "secretary")
    if mt.status != "ended":
        raise HTTPException(400, "end the meeting before approving its minutes")
    reviewer = officers.authority(db, user, org).has("review_minutes")
    if officers.review_required(db, org) and mt.review_status != "reviewed" and not reviewer:
        raise HTTPException(400, "an advisor needs to review these minutes before they are approved")
    if reviewer and mt.review_status != "reviewed":
        mt.review_status, mt.reviewed_by, mt.reviewed_at = "reviewed", user.id, time.time()
    mt.status, mt.approved_by, mt.approved_at, mt.updated_at = "approved", user.id, time.time(), time.time()
    audit.log(db, "meeting.approved", user, mt.org_id, client_ip(request), meeting=mt.id)
    db.commit()
    return meeting_payload(db, mt, role, user)


@router.post("/api/meetings/{meeting_id}/reopen")
def reopen(meeting_id: str, request: Request, user: models.User = Depends(current_user),
           db: Session = Depends(get_db)):
    mt, _, role = meeting_for(db, user, meeting_id, "secretary")
    if mt.status != "approved":
        raise HTTPException(400, "only approved minutes can be reopened")
    mt.status, mt.approved_by, mt.approved_at, mt.updated_at = "ended", None, None, time.time()
    mt.review_status, mt.reviewed_by, mt.reviewed_at = "", None, None
    audit.log(db, "meeting.reopened", user, mt.org_id, client_ip(request), meeting=mt.id)
    db.commit()
    return meeting_payload(db, mt, role, user)


class ReviewIn(BaseModel):
    action: str
    note: str = ""


@router.post("/api/meetings/{meeting_id}/review")
def review(meeting_id: str, body: ReviewIn, request: Request, user: models.User = Depends(current_user),
           db: Session = Depends(get_db)):
    if body.action == "request":
        mt, org, role = meeting_for(db, user, meeting_id, "secretary")
        if mt.status != "ended":
            raise HTTPException(400, "end the meeting before sending its minutes for review")
        if not officers.holders_with(db, org.id, "review_minutes"):
            raise HTTPException(400, "nobody in this organization reviews minutes yet; assign an advisor first")
        mt.review_status, mt.review_requested_at, mt.review_note = "requested", time.time(), body.note[:2000]
        mt.reviewed_by, mt.reviewed_at = None, None
    elif body.action in ("reviewed", "changes"):
        mt, org, role = meeting_for(db, user, meeting_id, "viewer")
        if not officers.authority(db, user, org).has("review_minutes"):
            raise HTTPException(403, "only advisors and others who review minutes can do this")
        if mt.status != "ended":
            raise HTTPException(400, "only minutes waiting for approval can be reviewed")
        if body.action == "changes" and not body.note.strip():
            raise HTTPException(400, "say what needs to change")
        mt.review_status, mt.review_note = body.action, body.note[:2000]
        mt.reviewed_by, mt.reviewed_at = user.id, time.time()
    else:
        raise HTTPException(400, "unknown review action")
    mt.updated_at = time.time()
    if body.action == "request":
        notify.review_requested(db, mt, user)
    else:
        notify.review_finished(db, mt, user)
    audit.log(db, "meeting.review_" + body.action, user, mt.org_id, client_ip(request), meeting=mt.id)
    db.commit()
    return meeting_payload(db, mt, role, user)


def export_data(mt, draft=None):
    day = re.sub(r",\s*\d{1,2}:\d{2}\s*[ap]\.m\.$", "", (mt.meeting_date or "").strip())
    place = mt.location or ("Zoom" if mt.zoom_url else "")
    return dict((mt.draft or {}) if draft is None else draft, fields={"lm_date": day, "lm_place": place})


def download_name(mt, ext):
    plain = unicodedata.normalize("NFKD", mt.title or "").encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^A-Za-z0-9_.\- ]+", "_", plain).strip(" ._")[:100] or "minutes"
    return "%s.%s" % (base, ext)


@router.post("/api/meetings/{meeting_id}/export")
def export_docx(meeting_id: str, request: Request, user: models.User = Depends(current_user),
                db: Session = Depends(get_db)):
    mt, org, _ = meeting_for(db, user, meeting_id, "member")
    tpl = db.get(models.Template, mt.template_id)
    work = storage.workdir()
    try:
        out = os.path.join(work, "minutes.docx")
        applied, failed = drafter.render(storage.store().local_copy(tpl.storage_key, work), export_data(mt), out)
        accessibility.set_properties(out, ("%s minutes: %s %s" % (org.name, mt.title, mt.meeting_date)).strip()[:250],
                                     "en-US")
        key = "orgs/%s/meetings/%s/minutes.docx" % (mt.org_id, mt.id)
        with open(out, "rb") as fh:
            storage.store().put(key, fh.read())
    finally:
        shutil.rmtree(work, ignore_errors=True)
    mt.export_key = key
    audit.log(db, "meeting.exported", user, mt.org_id, client_ip(request), meeting=mt.id)
    db.commit()
    return {"applied": len(applied), "skipped": failed, "download": "/api/meetings/%s/minutes.docx" % mt.id}


@router.get("/api/meetings/{meeting_id}/minutes.docx")
def download_docx(meeting_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    mt, _, _ = meeting_for(db, user, meeting_id, "member")
    if not mt.export_key:
        raise HTTPException(404, "build the Word file first")
    return Response(storage.store().get(mt.export_key),
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": 'attachment; filename="%s"' % download_name(mt, "docx")})


def _stamp(t, sep):
    t = max(0.0, t or 0.0)
    return "%02d:%02d:%02d%s%03d" % (int(t // 3600), int(t % 3600 // 60), int(t % 60), sep, int((t % 1) * 1000))


@router.get("/api/meetings/{meeting_id}/transcript.{fmt}")
def download_transcript(meeting_id: str, fmt: str, user: models.User = Depends(current_user),
                        db: Session = Depends(get_db)):
    mt, _, _ = meeting_for(db, user, meeting_id, "viewer")
    tr, _ = live.transcript_for(db, mt.id)
    return transcript_response(mt, tr.lines, fmt)


def transcript_response(mt, lines, fmt):
    if fmt == "txt":
        body, kind = "\n".join((ln.speaker + ": " if ln.speaker else "") + ln.text for ln in lines) + "\n", "text/plain"
    elif fmt in ("vtt", "srt"):
        sep = "." if fmt == "vtt" else ","
        out = ["WEBVTT", ""] if fmt == "vtt" else []
        for i, ln in enumerate(lines):
            start = ln.t or 0.0
            end = lines[i + 1].t if i + 1 < len(lines) and lines[i + 1].t else start + 4
            if fmt == "srt":
                out.append(str(i + 1))
            out.append("%s --> %s" % (_stamp(start, sep), _stamp(max(end, start + 0.5), sep)))
            out.append((ln.speaker + ": " if ln.speaker else "") + ln.text)
            out.append("")
        body, kind = "\n".join(out), "text/vtt" if fmt == "vtt" else "application/x-subrip"
    else:
        raise HTTPException(404, "use txt, vtt or srt")
    return Response(body.encode("utf-8"), media_type=kind + "; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="%s"' % download_name(mt, "transcript." + fmt)})


@router.delete("/api/meetings/{meeting_id}")
def delete_meeting(meeting_id: str, request: Request, user: models.User = Depends(current_user),
                   db: Session = Depends(get_db)):
    mt, org, _ = meeting_for(db, user, meeting_id, "owner")
    governance.check_hold(db, org, "delete this meeting")
    db.execute(delete(models.TranscriptLine).where(models.TranscriptLine.meeting_id == mt.id))
    db.execute(delete(models.ReferenceTranscript).where(models.ReferenceTranscript.meeting_id == mt.id))
    db.execute(delete(models.Job).where(models.Job.meeting_id == mt.id))
    db.execute(delete(models.DraftRevision).where(models.DraftRevision.meeting_id == mt.id))
    storage.store().delete_prefix("orgs/%s/meetings/%s" % (mt.org_id, mt.id))
    audit.log(db, "meeting.deleted", user, mt.org_id, client_ip(request), meeting=mt.id, title=mt.title)
    db.delete(mt)
    db.commit()
    return {"ok": True}
