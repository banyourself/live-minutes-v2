import datetime as dt
import time
import urllib.parse
from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones

from fastapi import HTTPException
from sqlalchemy import select

from . import models
from .settings import settings

HORIZON_DAYS = 70
PER_SERIES = 12
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth", -1: "last"}
ZOOM_HOSTS = ("zoom.us", "zoomgov.com")


@lru_cache(maxsize=1)
def zones():
    return frozenset(available_timezones())


def clean_tz(name):
    name = (name or "").strip()
    if name not in zones():
        raise HTTPException(400, "choose a valid time zone")
    return name


def clean_zoom_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    if len(url) > 500:
        raise HTTPException(400, "the Zoom link is too long")
    try:
        p = urllib.parse.urlsplit(url)
        host = (p.hostname or "").lower()
    except ValueError:
        raise HTTPException(400, "enter a Zoom meeting link")
    zoom = any(host == h or host.endswith("." + h) for h in ZOOM_HOSTS)
    if p.scheme != "https" or not zoom or p.username or p.password or p.port not in (None, 443):
        raise HTTPException(400, "use a Zoom meeting link, like https://zoom.us/j/123456789")
    return url


def clean_date(value, label):
    try:
        return dt.date.fromisoformat((value or "").strip()).isoformat()
    except ValueError:
        raise HTTPException(400, "enter the %s as a date" % label)


def clean_time(value):
    try:
        t = dt.time.fromisoformat((value or "").strip())
    except ValueError:
        raise HTTPException(400, "enter the start time, like 14:00")
    return "%02d:%02d" % (t.hour, t.minute)


def label_for(ts, tz):
    local = dt.datetime.fromtimestamp(ts, ZoneInfo(tz or "UTC"))
    hour = local.hour % 12 or 12
    return "%s, %s %d, %d, %d:%02d %s" % (WEEKDAYS[local.weekday()], local.strftime("%B"), local.day, local.year,
                                         hour, local.minute, "a.m." if local.hour < 12 else "p.m.")


def months_between(a, b):
    return (b.year - a.year) * 12 + b.month - a.month


def matches(series, day, start):
    if series.frequency == "weekly":
        weeks = ((day - (start - dt.timedelta(days=start.weekday()))).days // 7)
        return day.weekday() in (series.weekdays or []) and weeks % max(series.interval, 1) == 0
    if months_between(start, day) % max(series.interval, 1):
        return False
    if day.weekday() != series.month_weekday:
        return False
    if series.month_week == -1:
        return (day + dt.timedelta(days=7)).month != day.month
    return (day.day - 1) // 7 + 1 == series.month_week


def occurrences(series, from_ts, until_ts, limit=PER_SERIES):
    tz = ZoneInfo(series.timezone)
    start = dt.date.fromisoformat(series.start_date)
    last = dt.date.fromisoformat(series.until_date) if series.until_date else None
    hh, mm = (int(x) for x in series.start_time.split(":"))
    skip = set(series.skip_dates or [])
    day, out = max(start, dt.datetime.fromtimestamp(from_ts, tz).date()), []
    end_day = dt.datetime.fromtimestamp(until_ts, tz).date()
    while day <= end_day and len(out) < limit:
        if last is not None and day > last:
            break
        ts = dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz).timestamp()
        if day.isoformat() not in skip and ts >= from_ts and matches(series, day, start):
            out.append((day.isoformat(), ts))
        day += dt.timedelta(days=1)
    return out


def describe(series):
    when = "%d:%02d %s" % (int(series.start_time[:2]) % 12 or 12, int(series.start_time[3:]),
                           "a.m." if int(series.start_time[:2]) < 12 else "p.m.")
    if series.frequency == "weekly":
        days = " and ".join(WEEKDAYS[d] for d in sorted(series.weekdays or []))
        every = "Every" if series.interval == 1 else "Every %d weeks on" % series.interval
        text = "%s %s at %s" % (every, days, when)
    else:
        every = "month" if series.interval == 1 else "%d months" % series.interval
        text = "The %s %s of every %s at %s" % (ORDINALS.get(series.month_week, "first"),
                                                 WEEKDAYS[series.month_weekday], every, when)
    return text + (" until %s" % series.until_date if series.until_date else "")


def has_activity(db, meeting_id):
    return db.scalar(select(models.TranscriptLine.id).where(models.TranscriptLine.meeting_id == meeting_id).limit(1)) is not None


def clear_future(db, series, at=None):
    at = time.time() if at is None else at
    rows = db.scalars(select(models.Meeting).where(models.Meeting.series_id == series.id,
                                                   models.Meeting.status == "scheduled",
                                                   models.Meeting.scheduled_at > at)).all()
    n = 0
    for m in rows:
        if not has_activity(db, m.id):
            db.delete(m)
            n += 1
    db.flush()
    return n


def materialize(db, series, at=None):
    at = time.time() if at is None else at
    if not series.active or not series.template_id:
        return 0
    if db.get(models.Template, series.template_id) is None:
        return 0
    have = set(db.scalars(select(models.Meeting.scheduled_at).where(models.Meeting.series_id == series.id)).all())
    made = 0
    for _, ts in occurrences(series, at - 3600, at + HORIZON_DAYS * 86400, PER_SERIES * 2):
        if ts in have:
            continue
        db.add(models.Meeting(org_id=series.org_id, title=series.title, meeting_date=label_for(ts, series.timezone),
                              template_id=series.template_id, ai_connection_id=series.ai_connection_id,
                              run_mode=series.run_mode, notes=series.notes, status="scheduled", scheduled_at=ts,
                              duration_min=series.duration_min, timezone=series.timezone, zoom_url=series.zoom_url,
                              location=series.location, series_id=series.id, created_by=series.created_by,
                              visibility="private"))
        made += 1
        if made >= PER_SERIES:
            break
    db.flush()
    return made


def materialize_all(db, at=None):
    total = 0
    for series in db.scalars(select(models.MeetingSeries).where(models.MeetingSeries.active.is_(True))).all():
        total += materialize(db, series, at)
    return total


def ics_text(value):
    return (value or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def ics_fold(line):
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, cur = [], ""
    for ch in line:
        if len((cur + ch).encode("utf-8")) > (75 if not parts else 74):
            parts.append(cur)
            cur = ch
        else:
            cur += ch
    parts.append(cur)
    return "\r\n ".join(parts)


def ics_stamp(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ics(meetings, name="Live Minutes"):
    host = urllib.parse.urlsplit(settings.public_url).netloc or "live-minutes"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Live Minutes//Meetings//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "X-WR-CALNAME:" + ics_text(name)]
    stamp = ics_stamp(time.time())
    for m, org_name in meetings:
        if not m.scheduled_at:
            continue
        link = settings.public_url + "/meetings/" + m.id
        desc = ("Join on Zoom: %s\n" % m.zoom_url if m.zoom_url else "") + "Minutes: " + link
        lines += ["BEGIN:VEVENT", "UID:%s@%s" % (m.id, host), "DTSTAMP:" + stamp,
                  "DTSTART:" + ics_stamp(m.scheduled_at),
                  "DTEND:" + ics_stamp(m.scheduled_at + max(m.duration_min or 60, 5) * 60),
                  "SUMMARY:" + ics_text("%s: %s" % (org_name, m.title)),
                  "DESCRIPTION:" + ics_text(desc)]
        if m.location or m.zoom_url:
            lines.append("LOCATION:" + ics_text(m.location or m.zoom_url))
        if m.zoom_url:
            lines.append("URL:" + m.zoom_url)
        lines += ["STATUS:CONFIRMED", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(ics_fold(x) for x in lines) + "\r\n"
