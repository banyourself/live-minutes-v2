import datetime as dt
import time
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, models, ratelimit, runtime, scheduling
from ..db import get_db
from ..deps import client_ip, current_user, meeting_for, require_role
from ..security import new_token, token_hash
from ..settings import settings
from .meetings import check_conn, meeting_payload

router = APIRouter(tags=["calendar"])
MAX_SERIES = 50


class SeriesIn(BaseModel):
    title: str
    template_id: str
    ai_connection_id: str | None = None
    run_mode: str = "live"
    notes: str = ""
    notice_ack: bool = False
    frequency: str = "weekly"
    interval: int = 1
    weekdays: list[int] = []
    month_week: int = 1
    month_weekday: int = 0
    start_date: str
    until_date: str = ""
    start_time: str
    timezone: str
    duration_min: int = 60
    zoom_url: str = ""
    location: str = ""


class SeriesPatch(BaseModel):
    title: str | None = None
    zoom_url: str | None = None
    location: str | None = None
    start_time: str | None = None
    duration_min: int | None = None
    until_date: str | None = None
    notes: str | None = None


def check_series(db, org_id, body, user):
    title = " ".join((body.title or "").split())[:200]
    if len(title) < 2:
        raise HTTPException(400, "enter a title")
    tpl = db.get(models.Template, body.template_id)
    if tpl is None or tpl.org_id != org_id:
        raise HTTPException(400, "choose a template from this organization")
    if body.run_mode not in ("live", "after"):
        raise HTTPException(400, "mode must be live or after")
    if body.frequency not in ("weekly", "monthly"):
        raise HTTPException(400, "meetings can repeat weekly or monthly")
    if not 1 <= body.interval <= 12:
        raise HTTPException(400, "repeat every 1 to 12 weeks or months")
    days = sorted(set(body.weekdays))
    if body.frequency == "weekly" and (not days or any(d < 0 or d > 6 for d in days)):
        raise HTTPException(400, "choose the day or days of the week")
    if body.frequency == "monthly" and (body.month_week not in (1, 2, 3, 4, -1) or not 0 <= body.month_weekday <= 6):
        raise HTTPException(400, "choose which week and day of the month")
    start = scheduling.clean_date(body.start_date, "first date")
    until = scheduling.clean_date(body.until_date, "last date") if body.until_date else ""
    if until and until < start:
        raise HTTPException(400, "the last date must be after the first date")
    if dt.date.fromisoformat(start) > dt.date.today() + dt.timedelta(days=730):
        raise HTTPException(400, "the first meeting must be within two years")
    if not 5 <= body.duration_min <= 600:
        raise HTTPException(400, "meetings can last 5 minutes to 10 hours")
    return dict(title=title, template_id=tpl.id, ai_connection_id=check_conn(db, org_id, body.ai_connection_id, user),
                run_mode=body.run_mode, notes=(body.notes or "")[:6000], frequency=body.frequency,
                interval=body.interval, weekdays=days, month_week=body.month_week, month_weekday=body.month_weekday,
                start_date=start, until_date=until, start_time=scheduling.clean_time(body.start_time),
                timezone=scheduling.clean_tz(body.timezone), duration_min=body.duration_min,
                zoom_url=scheduling.clean_zoom_url(body.zoom_url), location=" ".join((body.location or "").split())[:200])


def series_row(db, s):
    nxt = db.scalar(select(models.Meeting.scheduled_at).where(models.Meeting.series_id == s.id,
                                                              models.Meeting.status == "scheduled")
                    .order_by(models.Meeting.scheduled_at).limit(1))
    return {"id": s.id, "title": s.title, "rule": scheduling.describe(s), "frequency": s.frequency, "interval": s.interval,
            "weekdays": s.weekdays or [], "month_week": s.month_week, "month_weekday": s.month_weekday,
            "start_date": s.start_date, "until_date": s.until_date, "start_time": s.start_time, "timezone": s.timezone,
            "duration_min": s.duration_min, "zoom_url": s.zoom_url, "location": s.location, "active": s.active,
            "next_at": nxt}


def summary(m):
    return {"id": m.id, "title": m.title, "meeting_date": m.meeting_date, "status": m.status, "run_mode": m.run_mode,
            "created_at": m.created_at, "approved_at": m.approved_at, "scheduled_at": m.scheduled_at,
            "duration_min": m.duration_min, "zoom_url": m.zoom_url, "location": m.location, "series_id": m.series_id, "sample": m.sample}


def series_in(db, org_id, series_id):
    s = db.get(models.MeetingSeries, series_id)
    if s is None or s.org_id != org_id:
        raise HTTPException(404, "recurring meeting not found")
    return s


@router.get("/api/orgs/{org_id}/calendar")
def org_calendar(org_id: str, start: float = 0.0, end: float = 0.0, user: models.User = Depends(current_user),
                 db: Session = Depends(get_db)):
    require_role(db, user, org_id, "viewer")
    now = time.time()
    start = start or now - 31 * 86400
    end = min(end or now + 62 * 86400, start + 400 * 86400)
    rows = db.scalars(select(models.Meeting).where(models.Meeting.org_id == org_id,
                                                   models.Meeting.scheduled_at >= start,
                                                   models.Meeting.scheduled_at < end)
                      .order_by(models.Meeting.scheduled_at).limit(500)).all()
    series = db.scalars(select(models.MeetingSeries).where(models.MeetingSeries.org_id == org_id,
                                                           models.MeetingSeries.active.is_(True))
                        .order_by(models.MeetingSeries.created_at)).all()
    return {"meetings": [summary(m) for m in rows], "series": [series_row(db, s) for s in series]}


@router.post("/api/orgs/{org_id}/series")
def create_series(org_id: str, body: SeriesIn, request: Request, user: models.User = Depends(current_user),
                  db: Session = Depends(get_db)):
    require_role(db, user, org_id, "secretary")
    count = len(db.scalars(select(models.MeetingSeries.id).where(models.MeetingSeries.org_id == org_id,
                                                                 models.MeetingSeries.active.is_(True))).all())
    if count >= MAX_SERIES:
        raise HTTPException(400, "an organization can have up to %d recurring meetings" % MAX_SERIES)
    s = models.MeetingSeries(org_id=org_id, created_by=user.id, **check_series(db, org_id, body, user))
    db.add(s)
    db.flush()
    made = scheduling.materialize(db, s)
    audit.log(db, "series.created", user, org_id, client_ip(request), series=s.id, rule=scheduling.describe(s),
              notice_ack=body.notice_ack)
    db.commit()
    return dict(series_row(db, s), scheduled=made)


@router.patch("/api/orgs/{org_id}/series/{series_id}")
def edit_series(org_id: str, series_id: str, body: SeriesPatch, request: Request,
                user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, org_id, "secretary")
    s = series_in(db, org_id, series_id)
    if body.title is not None:
        title = " ".join(body.title.split())[:200]
        if len(title) < 2:
            raise HTTPException(400, "enter a title")
        s.title = title
    if body.zoom_url is not None:
        s.zoom_url = scheduling.clean_zoom_url(body.zoom_url)
    if body.location is not None:
        s.location = " ".join(body.location.split())[:200]
    if body.start_time is not None:
        s.start_time = scheduling.clean_time(body.start_time)
    if body.duration_min is not None:
        if not 5 <= body.duration_min <= 600:
            raise HTTPException(400, "meetings can last 5 minutes to 10 hours")
        s.duration_min = body.duration_min
    if body.until_date is not None:
        until = scheduling.clean_date(body.until_date, "last date") if body.until_date else ""
        if until and until < s.start_date:
            raise HTTPException(400, "the last date must be after the first date")
        s.until_date = until
    if body.notes is not None:
        s.notes = body.notes[:6000]
    scheduling.clear_future(db, s)
    scheduling.materialize(db, s)
    audit.log(db, "series.edited", user, org_id, client_ip(request), series=s.id, rule=scheduling.describe(s))
    db.commit()
    return series_row(db, s)


@router.delete("/api/orgs/{org_id}/series/{series_id}")
def stop_series(org_id: str, series_id: str, request: Request, user: models.User = Depends(current_user),
                db: Session = Depends(get_db)):
    require_role(db, user, org_id, "secretary")
    s = series_in(db, org_id, series_id)
    s.active = False
    removed = scheduling.clear_future(db, s)
    audit.log(db, "series.stopped", user, org_id, client_ip(request), series=s.id, removed=removed)
    db.commit()
    return {"ok": True, "removed": removed}


@router.post("/api/meetings/{meeting_id}/start")
def start_meeting(meeting_id: str, request: Request, user: models.User = Depends(current_user),
                  db: Session = Depends(get_db)):
    mt, _, role = meeting_for(db, user, meeting_id, "secretary")
    if mt.status != "scheduled":
        raise HTTPException(400, "this meeting has already started")
    mt.status, mt.updated_at = "open", time.time()
    audit.log(db, "meeting.started", user, mt.org_id, client_ip(request), meeting=mt.id)
    db.commit()
    return meeting_payload(db, mt, role, user)


@router.post("/api/meetings/{meeting_id}/cancel")
def cancel_meeting(meeting_id: str, request: Request, user: models.User = Depends(current_user),
                   db: Session = Depends(get_db)):
    mt, _, _ = meeting_for(db, user, meeting_id, "secretary")
    if mt.status != "scheduled":
        raise HTTPException(400, "only meetings that have not started can be canceled")
    if scheduling.has_activity(db, mt.id):
        raise HTTPException(400, "this meeting already has a transcript; delete it instead")
    if mt.series_id and mt.scheduled_at:
        s = db.get(models.MeetingSeries, mt.series_id)
        if s is not None:
            local = dt.datetime.fromtimestamp(mt.scheduled_at, ZoneInfo(s.timezone)).date().isoformat()
            s.skip_dates = sorted(set(s.skip_dates or []) | {local})[-200:]
    audit.log(db, "meeting.canceled", user, mt.org_id, client_ip(request), meeting=mt.id, title=mt.title,
              scheduled_at=mt.scheduled_at)
    db.delete(mt)
    db.commit()
    return {"ok": True}


def ics_response(text, filename):
    return Response(text, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="%s"' % filename,
                             "Cache-Control": "private, max-age=300"})


@router.get("/api/meetings/{meeting_id}/invite.ics")
def meeting_ics(meeting_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    mt, org, _ = meeting_for(db, user, meeting_id, "viewer")
    if not mt.scheduled_at:
        raise HTTPException(400, "this meeting has no scheduled time")
    return ics_response(scheduling.ics([(mt, org.name)], org.name), "meeting.ics")


@router.get("/api/me/calendar-feed")
def feed_status(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    f = db.scalar(select(models.CalendarFeed).where(models.CalendarFeed.user_id == user.id))
    return {"enabled": f is not None, "created_at": f.created_at if f else None,
            "last_used_at": f.last_used_at if f else None}


@router.post("/api/me/calendar-feed")
def feed_create(request: Request, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ratelimit.hit("calendar-feed:" + user.id, 10, 86400, "you made several feed links today; try again tomorrow")
    f = db.scalar(select(models.CalendarFeed).where(models.CalendarFeed.user_id == user.id))
    token = new_token()
    if f is None:
        f = models.CalendarFeed(user_id=user.id, token_hash=token_hash("calendar:" + token))
        db.add(f)
    else:
        f.token_hash, f.created_at, f.last_used_at = token_hash("calendar:" + token), time.time(), None
    audit.log(db, "calendar.feed_created", user, ip=client_ip(request))
    db.commit()
    return {"url": settings.public_url + "/api/calendar/" + token + ".ics"}


@router.delete("/api/me/calendar-feed")
def feed_delete(request: Request, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    f = db.scalar(select(models.CalendarFeed).where(models.CalendarFeed.user_id == user.id))
    if f is not None:
        db.delete(f)
        audit.log(db, "calendar.feed_removed", user, ip=client_ip(request))
        db.commit()
    return {"ok": True}


@router.get("/api/calendar/{token}.ics")
def feed(token: str, request: Request, db: Session = Depends(get_db)):
    key = "calendar-bad:" + client_ip(request)
    if ratelimit.blocked(key, 30, 600):
        raise HTTPException(429, "too many invalid calendar links; wait a few minutes")
    f = db.scalar(select(models.CalendarFeed).where(models.CalendarFeed.token_hash == token_hash("calendar:" + token)))
    user = db.get(models.User, f.user_id) if f is not None else None
    if user is None or user.disabled or user.email_verified_at is None:
        ratelimit.record(key)
        raise HTTPException(404, "this calendar link is not valid; make a new one under My account")
    if runtime.get("maintenance_mode"):
        raise HTTPException(503, "Live Minutes is down for maintenance; try again soon")
    now = time.time()
    rows = db.execute(select(models.Meeting, models.Organization.name)
                      .join(models.Organization, models.Organization.id == models.Meeting.org_id)
                      .join(models.Membership, (models.Membership.org_id == models.Meeting.org_id)
                            & (models.Membership.user_id == user.id))
                      .where(models.Meeting.scheduled_at >= now - 90 * 86400,
                             models.Meeting.scheduled_at < now + 180 * 86400)
                      .order_by(models.Meeting.scheduled_at).limit(500)).all()
    if not f.last_used_at or now - f.last_used_at > 600:
        f.last_used_at = now
    db.commit()
    return ics_response(scheduling.ics(rows, "Live Minutes"), "live-minutes.ics")
