import datetime as dt
import time

from sqlalchemy import delete, select

from . import mailer, models
from .settings import settings

LABELS = {
    "draft_ready": "Draft minutes are ready, or drafting failed",
    "review_needed": "Minutes are waiting for my review",
    "review_done": "Minutes I run were reviewed or need changes",
    "reminder": "A reminder the day before a scheduled meeting",
    "digest": "Email me the weekly summary (it is always under This week)",
    "officer": "My officer position starts or ends",
}
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
DIGEST_HOUR_UTC = 15


def prefs(db, user_id):
    p = db.get(models.NotificationPref, user_id)
    return p if p is not None else models.NotificationPref(user_id=user_id, email={}, digest_weekday=0, last_digest_at=0.0)


OFF_BY_DEFAULT = ("digest",)


def wants_email(p, kind):
    return bool((p.email or {}).get(kind, kind not in OFF_BY_DEFAULT))


def active(u):
    return u is not None and not u.disabled and u.email_verified_at is not None


def send(db, users, kind, org, title, body, link="", skip=None):
    seen, n = set(), 0
    for u in users:
        if not active(u) or u.id in seen or (skip is not None and u.id == skip):
            continue
        seen.add(u.id)
        p = prefs(db, u.id)
        if kind == "digest" and not wants_email(p, kind):
            continue
        db.add(models.Notification(user_id=u.id, org_id=org.id if org else None, kind=kind, title=title[:300],
                                   body=body[:6000], link=link[:300]))
        if wants_email(p, kind):
            mailer.queue(db, u.email, title[:200], body + ("\n\nOpen it: %s%s" % (settings.public_url, link) if link else "") +
                         "\n\nChoose which emails you get under My account, Notifications: %s/account?tab=notifications" % settings.public_url)
        n += 1
    return n


def members(db, org, minimum="viewer"):
    from . import officers
    rows = db.execute(select(models.Membership, models.User).join(models.User, models.User.id == models.Membership.user_id)
                      .where(models.Membership.org_id == org.id)).all()
    need = models.ROLE_RANK[minimum]
    return [u for m, u in rows if models.ROLE_RANK.get(officers.effective_role(db, m), 0) >= need]


def reviewers(db, org):
    from . import officers
    ids = {t.user_id for t, _ in officers.holders_with(db, org.id, "review_minutes")}
    return [u for u in (db.get(models.User, i) for i in ids) if u is not None]


def draft_ready(db, meeting, ok=True, error=""):
    org = db.get(models.Organization, meeting.org_id)
    link = "/meetings/" + meeting.id
    if ok:
        title = "Draft minutes ready: %s" % meeting.title
        body = "The AI finished the draft minutes for %s (%s) in %s. Review them before approval." % (
            meeting.title, meeting.meeting_date or "no date", org.name)
    else:
        title = "Drafting failed: %s" % meeting.title
        body = "The AI could not draft the minutes for %s in %s: %s" % (meeting.title, org.name, error[:300])
    return send(db, members(db, org, "secretary"), "draft_ready", org, title, body, link)


def review_requested(db, meeting, actor):
    org = db.get(models.Organization, meeting.org_id)
    return send(db, reviewers(db, org), "review_needed", org, "Minutes to review: %s" % meeting.title,
                "%s asked you to review the minutes for %s (%s) in %s before they are approved.%s" % (
                    actor.name or actor.email, meeting.title, meeting.meeting_date or "no date", org.name,
                    "\n\nNote: " + meeting.review_note if meeting.review_note else ""),
                "/meetings/" + meeting.id, skip=actor.id)


def review_finished(db, meeting, actor):
    org = db.get(models.Organization, meeting.org_id)
    if meeting.review_status == "reviewed":
        title, what = "Minutes reviewed: %s" % meeting.title, "reviewed the minutes; they can be approved now"
    else:
        title, what = "Changes requested: %s" % meeting.title, "asked for changes before approval"
    body = "%s %s for %s (%s) in %s.%s" % (actor.name or actor.email, what, meeting.title, meeting.meeting_date or "no date",
                                          org.name, "\n\n" + meeting.review_note if meeting.review_note else "")
    return send(db, members(db, org, "secretary"), "review_done", org, title, body, "/meetings/" + meeting.id, skip=actor.id)


def officer(db, org, user, title, body):
    return send(db, [user], "officer", org, title, body, "/settings")


def remind(db, at=None):
    from . import scheduling
    at = time.time() if at is None else at
    rows = db.scalars(select(models.Meeting).where(models.Meeting.status == "scheduled",
                                                   models.Meeting.sample.is_(False),
                                                   models.Meeting.reminded_at.is_(None),
                                                   models.Meeting.scheduled_at > at,
                                                   models.Meeting.scheduled_at <= at + 86400)).all()
    for m in rows:
        org = db.get(models.Organization, m.org_id)
        when = scheduling.label_for(m.scheduled_at, m.timezone or "UTC")
        body = "%s meets %s%s" % (org.name, when, "" if when.endswith(".") else ".") + \
            (" Join on Zoom: %s" % m.zoom_url if m.zoom_url else "") + (" Location: %s." % m.location if m.location else "")
        send(db, members(db, org), "reminder", org, "Coming up: %s" % m.title, body, "/meetings/" + m.id)
        m.reminded_at = at
    return len(rows)


def digest_for(db, user, at):
    return "\n\n".join(s["org"] + "\n" + "\n".join("- " + i["text"] for i in s["items"]) for s in week_for(db, user, at))


def week_for(db, user, at):
    week = at - 7 * 86400
    parts = []
    rows = db.execute(select(models.Membership, models.Organization)
                      .join(models.Organization, models.Organization.id == models.Membership.org_id)
                      .where(models.Membership.user_id == user.id)).all()
    from . import officers
    for m, org in rows:
        role = officers.effective_role(db, m)
        meets = db.scalars(select(models.Meeting).where(models.Meeting.org_id == org.id, models.Meeting.sample.is_(False))).all()
        approved = [x for x in meets if x.approved_at and x.approved_at >= week]
        held = [x for x in meets if x.status in ("ended", "approved") and (x.scheduled_at or x.created_at) >= week]
        upcoming = sorted([x for x in meets if x.status == "scheduled" and at <= (x.scheduled_at or 0) < at + 7 * 86400],
                          key=lambda x: x.scheduled_at)
        items = []
        add = lambda kind, text, link="": items.append({"kind": kind, "text": text.replace("..", "."), "link": link})
        for x in held[:8]:
            add("held", "Met: %s, %s." % (x.title, x.meeting_date or "no date"), "/meetings/" + x.id)
        for x in approved[:8]:
            summary = (x.plain_summary or "").strip()
            add("approved", "Minutes approved: %s." % x.title + ("\n" + summary if summary else ""), "/meetings/" + x.id)
        if models.ROLE_RANK.get(role, 0) >= models.ROLE_RANK["secretary"]:
            for x in [x for x in meets if x.status == "ended"][:8]:
                add("waiting", "Waiting for approval: %s." % x.title, "/meetings/" + x.id)
        if officers.authority(db, user, org).has("review_minutes") and not officers.authority(db, user, org).above:
            for x in [x for x in meets if x.status == "ended" and x.review_status == "requested"][:8]:
                add("review", "Waiting for your review: %s." % x.title, "/meetings/" + x.id)
        for x in upcoming[:8]:
            add("upcoming", "Coming up: %s, %s." % (x.title, x.meeting_date), "/meetings/" + x.id)
        pending = db.scalars(select(models.FundingRequest.id).where(models.FundingRequest.org_id == org.id,
                                                                    models.FundingRequest.status.in_(("submitted", "in_review")))).all()
        if pending:
            add("funding", "%d funding request%s waiting." % (len(pending), "" if len(pending) == 1 else "s"), "/funding")
        if items:
            parts.append({"org_id": org.id, "org": org.name, "items": items})
    return parts


def digests(db, at=None):
    at = time.time() if at is None else at
    now = dt.datetime.fromtimestamp(at, dt.timezone.utc)
    if now.hour < DIGEST_HOUR_UTC:
        return 0
    ids = set(db.scalars(select(models.Membership.user_id)).all())
    sent = 0
    for uid in ids:
        user = db.get(models.User, uid)
        if not active(user):
            continue
        p = db.get(models.NotificationPref, uid)
        if p is None or not wants_email(p, "digest"):
            continue
        if now.weekday() != p.digest_weekday or at - (p.last_digest_at or 0.0) < 6 * 86400:
            continue
        p.last_digest_at = at
        text = digest_for(db, user, at)
        if text and wants_email(p, "digest"):
            sent += send(db, [user], "digest", None, "Your week on Live Minutes", text, "/week")
    return sent


def purge(db, at=None):
    at = time.time() if at is None else at
    db.execute(delete(models.Notification).where(models.Notification.created_at < at - 180 * 86400))
