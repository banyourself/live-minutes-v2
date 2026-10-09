import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import models, notify
from ..db import get_db
from ..deps import current_user

router = APIRouter(prefix="/api/me", tags=["notifications"])


class ReadIn(BaseModel):
    ids: list[str] = []
    all: bool = False


class PrefsIn(BaseModel):
    email: dict[str, bool] = {}
    digest_weekday: int | None = None


def unread(db, user):
    return db.scalar(select(func.count()).select_from(models.Notification)
                     .where(models.Notification.user_id == user.id, models.Notification.read_at.is_(None))) or 0


@router.get("/notifications")
def list_notifications(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(models.Notification).where(models.Notification.user_id == user.id)
                      .order_by(models.Notification.created_at.desc()).limit(100)).all()
    names = {o.id: o.name for o in db.scalars(select(models.Organization).where(
        models.Organization.id.in_({r.org_id for r in rows if r.org_id} or {""}))).all()}
    return {"unread": unread(db, user),
            "notifications": [{"id": r.id, "kind": r.kind, "title": r.title, "body": r.body, "link": r.link,
                               "org": names.get(r.org_id, ""), "created_at": r.created_at, "read": r.read_at is not None}
                              for r in rows]}


@router.get("/notifications/count")
def count(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return {"unread": unread(db, user)}


@router.post("/notifications/read")
def mark_read(body: ReadIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    q = update(models.Notification).where(models.Notification.user_id == user.id,
                                          models.Notification.read_at.is_(None))
    if not body.all:
        if not body.ids:
            return {"unread": unread(db, user)}
        q = q.where(models.Notification.id.in_(body.ids[:200]))
    db.execute(q.values(read_at=time.time()))
    db.commit()
    return {"unread": unread(db, user)}


@router.get("/week")
def this_week(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    now = time.time()
    return {"start": now - 7 * 86400, "end": now + 7 * 86400, "orgs": notify.week_for(db, user, now)}


@router.get("/notification-prefs")
def get_prefs(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    p = notify.prefs(db, user.id)
    return {"email": {k: notify.wants_email(p, k) for k in models.NOTIFY_KINDS}, "digest_weekday": p.digest_weekday,
            "labels": [{"id": k, "label": notify.LABELS[k]} for k in models.NOTIFY_KINDS], "days": list(notify.DAYS)}


@router.put("/notification-prefs")
def put_prefs(body: PrefsIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if any(k not in models.NOTIFY_KINDS for k in body.email):
        raise HTTPException(400, "unknown notification type")
    if body.digest_weekday is not None and not 0 <= body.digest_weekday <= 6:
        raise HTTPException(400, "choose a day of the week")
    p = db.get(models.NotificationPref, user.id)
    if p is None:
        p = models.NotificationPref(user_id=user.id, email={}, digest_weekday=0, last_digest_at=0.0)
        db.add(p)
    p.email = dict(p.email or {}, **{k: bool(v) for k, v in body.email.items()})
    if body.digest_weekday is not None:
        p.digest_weekday = body.digest_weekday
    db.commit()
    return get_prefs(user, db)
