import shutil

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from minutes_app import drafter, template as tpl_engine

from .. import audit, governance, history, models, personal, samples, storage
from ..db import get_db
from ..deps import client_ip, current_user, require_role
from .meetings import default_conn
from .templates import save_generated

router = APIRouter(prefix="/api/orgs/{org_id}/sample-meetings", tags=["sample meetings"])
MAX_SAMPLES = 40
SKIP = ("call to order", "adjourn", "welcome", "start of meeting", "wrap-up", "closing")


class SampleIn(BaseModel):
    count: int = 5
    seed: int | None = None
    length: str = "standard"
    minutes: int | None = None


def template_for(db, org, user):
    cfg = org.settings or {}
    t = db.get(models.Template, cfg.get("default_template_id") or "")
    if t is None or t.org_id != org.id or t.purpose != "template":
        t = db.scalar(select(models.Template).where(models.Template.org_id == org.id, models.Template.purpose == "template")
                      .order_by(models.Template.created_at))
    if t is not None:
        return t
    key = "modern" if personal.is_personal(db, org.id) else "student-government"
    design = dict(tpl_engine.preset(key, org.name + " Minutes"), name=tpl_engine.BUILTIN[key]["name"])
    t = models.Template(org_id=org.id, name=design["name"], filename=key + ".docx", storage_key="",
                        mode="generated", purpose="template", design=design, created_by=user.id)
    db.add(t)
    db.flush()
    work = storage.workdir()
    try:
        save_generated(t, design, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return t


def slots_for(t):
    work = storage.workdir()
    try:
        slots = drafter.template_outline(storage.store().local_copy(t.storage_key, work))["slots"]
    finally:
        shutil.rmtree(work, ignore_errors=True)
    design = t.design or {}
    fixed = {str(design.get("first_item", "")).lower(), str(design.get("last_item", "")).lower()}
    keep = [s for s in slots if s.lower() not in fixed and not any(w in s.lower() for w in SKIP)]
    return keep or ["Discussion", "New Business", "Announcements"]


@router.get("")
def count(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, org_id, "member")
    n = db.scalar(select(func.count()).select_from(models.Meeting).where(models.Meeting.org_id == org_id,
                                                                         models.Meeting.sample.is_(True)))
    return {"count": int(n or 0), "max": MAX_SAMPLES}


@router.post("")
def make(org_id: str, body: SampleIn, request: Request, user: models.User = Depends(current_user),
         db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "secretary")
    if not 1 <= body.count <= 10:
        raise HTTPException(400, "make 1 to 10 sample meetings at a time")
    if body.length not in ("short", "standard", "long", "mixed", "custom"):
        raise HTTPException(400, "choose short, standard, long, mixed, or a number of minutes")
    if body.length == "custom" and not (body.minutes and 10 <= body.minutes <= 120):
        raise HTTPException(400, "choose a length from 10 to 120 minutes")
    have = count(org_id, user, db)["count"]
    if have + body.count > MAX_SAMPLES:
        raise HTTPException(400, "an organization can have up to %d sample meetings; remove some first" % MAX_SAMPLES)
    t = template_for(db, org, user)
    made = samples.make(db, org, user, t, slots_for(t), body.count, body.seed, body.length,
                        body.minutes if body.length == "custom" else None, personal.is_personal(db, org.id))
    conn = default_conn(db, user, org.id)
    for mt in made:
        mt.ai_connection_id = conn
        if mt.draft:
            history.record(db, mt, {}, "ai", None, "Sample draft")
    audit.log(db, "meeting.samples_created", user, org.id, client_ip(request), count=len(made))
    db.commit()
    return {"meetings": [{"id": m.id, "title": m.title, "status": m.status, "drafted": bool(m.draft),
                          "minutes": m.duration_min} for m in made]}


@router.delete("")
def remove(org_id: str, request: Request, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "secretary")
    governance.check_hold(db, org, "remove sample meetings")
    rows = db.scalars(select(models.Meeting).where(models.Meeting.org_id == org_id, models.Meeting.sample.is_(True))).all()
    for mt in rows:
        governance.remove_meeting(db, mt)
    audit.log(db, "meeting.samples_removed", user, org.id, client_ip(request), count=len(rows))
    db.commit()
    return {"removed": len(rows)}
