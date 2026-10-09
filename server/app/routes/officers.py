import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, models, notify, officers, scheduling
from ..db import get_db
from ..deps import client_ip, current_user, require_role

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["officers"])


class PositionIn(BaseModel):
    name: str
    rank: int = 50
    access: str = "member"
    permissions: list[str] = []
    account_types: list[str] = []
    max_holders: int = 0


class PositionPatch(BaseModel):
    name: str | None = None
    rank: int | None = None
    access: str | None = None
    permissions: list[str] | None = None
    account_types: list[str] | None = None
    max_holders: int | None = None


class SettingsIn(BaseModel):
    owners_manage_officers: bool | None = None
    require_review: bool | None = None


class TermIn(BaseModel):
    position_id: str
    user_id: str
    starts_at: float | None = None
    ends_at: float | None = None
    remove_at_end: bool = False


class TermPatch(BaseModel):
    ends_at: float | None = None
    remove_at_end: bool = False


def load(db, user, org_id):
    org, _ = require_role(db, user, org_id, "member")
    rows = officers.positions(db, org)
    return org, rows, officers.authority(db, user, org, rows)


def position_in(db, org_id, position_id):
    pos = db.get(models.Position, position_id)
    if pos is None or pos.org_id != org_id:
        raise HTTPException(404, "position not found")
    return pos


def term_in(db, org_id, term_id):
    t = db.get(models.PositionTerm, term_id)
    if t is None or t.org_id != org_id:
        raise HTTPException(404, "term not found")
    return t


def name_taken(db, org_id, name, skip_id=None):
    rows = db.scalars(select(models.Position).where(models.Position.org_id == org_id)).all()
    return any(p.name.lower() == name.lower() and p.id != skip_id for p in rows)


def term_row(t, p, u, auth, user, db, org):
    return {"id": t.id, "position_id": p.id, "position": p.name, "rank": p.rank, "user_id": t.user_id,
            "name": u.name if u else "", "email": u.email if u else "", "starts_at": t.starts_at,
            "ends_at": t.ends_at, "remove_at_end": t.remove_at_end, "state": officers.term_state(t),
            "ended_at": t.ended_at, "end_reason": t.end_reason,
            "can_end": officers.term_state(t) != "ended" and officers.can_end(auth, t, p, user),
            "can_change": officers.term_state(t) != "ended" and officers.can_assign(db, auth, org, p)}


@router.get("/officers")
def overview(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    org, rows, auth = load(db, user, org_id)
    by_id = {p.id: p for p in rows}
    terms = db.scalars(select(models.PositionTerm).where(models.PositionTerm.org_id == org_id)
                       .order_by(models.PositionTerm.starts_at.desc()).limit(400)).all()
    people = {u.id: u for u in db.scalars(select(models.User).where(
        models.User.id.in_({t.user_id for t in terms} or {""}))).all()}
    current, past = [], []
    for t in terms:
        p = by_id.get(t.position_id)
        if p is None:
            continue
        row = term_row(t, p, people.get(t.user_id), auth, user, db, org)
        (past if row["state"] == "ended" else current).append(row)
    current.sort(key=lambda r: (-r["rank"], r["position"], r["starts_at"]))
    counts = {}
    for r in current:
        if r["state"] == "active":
            counts[r["position_id"]] = counts.get(r["position_id"], 0) + 1
    db.commit()
    return {"positions": [{"id": p.id, "name": p.name, "rank": p.rank, "access": p.access,
                           "permissions": p.permissions or [], "account_types": p.account_types or [],
                           "max_holders": p.max_holders, "holders": counts.get(p.id, 0),
                           "can_edit": officers.can_edit(auth, p),
                           "can_assign": officers.can_assign(db, auth, org, p)} for p in rows],
            "terms": current, "history": past[:100], "settings": officers.org_cfg(org),
            "permission_labels": [{"id": k, "label": v} for k, v in officers.LABELS.items()],
            "me": {"can_edit_permissions": auth.has("edit_permissions"), "above": auth.above,
                   "edit_rank": auth.rank("edit_permissions") if auth.has("edit_permissions") else None,
                   "permissions": sorted(auth.permissions()), "access": auth.access,
                   "positions": [p.name for _, p in officers.held(db, org_id, user.id)]}}


@router.post("/positions")
def create_position(org_id: str, body: PositionIn, request: Request, user: models.User = Depends(current_user),
                    db: Session = Depends(get_db)):
    org, rows, auth = load(db, user, org_id)
    officers.need_editor(auth)
    name, rank, access, perms, types, most = officers.check_position(auth, body.name, body.rank, body.access,
                                                                     body.permissions, body.account_types,
                                                                     body.max_holders)
    if name_taken(db, org_id, name):
        raise HTTPException(409, "there is already a position named %s" % name)
    if len(rows) >= 60:
        raise HTTPException(400, "an organization can have up to 60 positions")
    pos = models.Position(org_id=org_id, name=name, rank=rank, access=access, permissions=perms,
                          account_types=types, max_holders=most)
    db.add(pos)
    audit.log(db, "officer.position_created", user, org_id, client_ip(request), position=name, rank=rank,
              access=access, permissions=",".join(perms))
    db.commit()
    return {"id": pos.id}


@router.patch("/positions/{position_id}")
def edit_position(org_id: str, position_id: str, body: PositionPatch, request: Request,
                  user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    org, rows, auth = load(db, user, org_id)
    officers.need_editor(auth)
    pos = position_in(db, org_id, position_id)
    if not officers.can_edit(auth, pos):
        raise HTTPException(403, "you can only edit positions ranked below your own")
    name, rank, access, perms, types, most = officers.check_position(
        auth, body.name if body.name is not None else pos.name, body.rank if body.rank is not None else pos.rank,
        body.access or pos.access, body.permissions if body.permissions is not None else pos.permissions,
        body.account_types if body.account_types is not None else pos.account_types,
        body.max_holders if body.max_holders is not None else pos.max_holders)
    if name_taken(db, org_id, name, pos.id):
        raise HTTPException(409, "there is already a position named %s" % name)
    before = {"name": pos.name, "rank": pos.rank, "access": pos.access, "permissions": ",".join(pos.permissions or [])}
    pos.name, pos.rank, pos.access, pos.permissions, pos.account_types, pos.max_holders = (
        name, rank, access, perms, types, most)
    audit.log(db, "officer.position_edited", user, org_id, client_ip(request), position=name, before=before,
              rank=rank, access=access, permissions=",".join(perms))
    db.commit()
    return {"ok": True}


@router.delete("/positions/{position_id}")
def delete_position(org_id: str, position_id: str, request: Request, user: models.User = Depends(current_user),
                    db: Session = Depends(get_db)):
    org, rows, auth = load(db, user, org_id)
    officers.need_editor(auth)
    pos = position_in(db, org_id, position_id)
    if not officers.can_edit(auth, pos):
        raise HTTPException(403, "you can only remove positions ranked below your own")
    audit.log(db, "officer.position_removed", user, org_id, client_ip(request), position=pos.name)
    db.delete(pos)
    db.commit()
    return {"ok": True}


@router.put("/officer-settings")
def save_settings(org_id: str, body: SettingsIn, request: Request, user: models.User = Depends(current_user),
                  db: Session = Depends(get_db)):
    org, _, auth = load(db, user, org_id)
    officers.need_editor(auth)
    cfg = dict(org.settings or {})
    if body.owners_manage_officers is not None:
        cfg["owners_manage_officers"] = body.owners_manage_officers
    if body.require_review is not None:
        cfg["require_review"] = body.require_review
    org.settings = cfg
    audit.log(db, "officer.settings", user, org_id, client_ip(request), **officers.org_cfg(org))
    db.commit()
    return officers.org_cfg(org)


@router.post("/terms")
def assign(org_id: str, body: TermIn, request: Request, user: models.User = Depends(current_user),
           db: Session = Depends(get_db)):
    org, _, auth = load(db, user, org_id)
    pos = position_in(db, org_id, body.position_id)
    if not officers.can_assign(db, auth, org, pos):
        raise HTTPException(403, "you cannot assign %s" % pos.name)
    who = db.get(models.User, body.user_id)
    if who is None or officers.membership(db, org_id, body.user_id) is None:
        raise HTTPException(400, "add this person to the organization first")
    if who.disabled:
        raise HTTPException(400, "this account is disabled")
    officers.check_holder(db, org, pos, who)
    start = body.starts_at if body.starts_at is not None else time.time()
    officers.check_window(db, pos, who.id, start, body.ends_at)
    t = models.PositionTerm(org_id=org_id, position_id=pos.id, user_id=who.id, starts_at=start,
                            ends_at=body.ends_at, remove_at_end=body.remove_at_end, assigned_by=user.id)
    db.add(t)
    term = ("until %s" % scheduling.label_for(body.ends_at, "UTC").rsplit(",", 1)[0]) if body.ends_at else "with no end date"
    notify.officer(db, org, who, "You are now %s in %s" % (pos.name[:80], org.name[:120]),
                   "%s made you %s in %s, %s.%s" % (user.name or user.email, pos.name, org.name, term,
                                                    " You will leave the organization when the term ends."
                                                    if body.remove_at_end else ""))
    audit.log(db, "officer.assigned", user, org_id, client_ip(request), position=pos.name, member=who.id,
              email=who.email, starts_at=start, ends_at=body.ends_at, remove_at_end=body.remove_at_end)
    db.commit()
    return {"id": t.id}


@router.patch("/terms/{term_id}")
def change_term(org_id: str, term_id: str, body: TermPatch, request: Request,
                user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    org, _, auth = load(db, user, org_id)
    t = term_in(db, org_id, term_id)
    pos = position_in(db, org_id, t.position_id)
    if officers.term_state(t) == "ended":
        raise HTTPException(400, "this term has already ended")
    if not officers.can_assign(db, auth, org, pos):
        raise HTTPException(403, "you cannot change terms for %s" % pos.name)
    officers.check_window(db, pos, t.user_id, t.starts_at, body.ends_at, skip_id=t.id)
    t.ends_at, t.remove_at_end = body.ends_at, body.remove_at_end
    audit.log(db, "officer.term_changed", user, org_id, client_ip(request), position=pos.name, member=t.user_id,
              ends_at=body.ends_at, remove_at_end=body.remove_at_end)
    db.commit()
    return {"ok": True}


@router.post("/terms/{term_id}/end")
def end(org_id: str, term_id: str, request: Request, user: models.User = Depends(current_user),
        db: Session = Depends(get_db)):
    org, _, auth = load(db, user, org_id)
    t = term_in(db, org_id, term_id)
    pos = position_in(db, org_id, t.position_id)
    if officers.term_state(t) == "ended":
        raise HTTPException(400, "this term has already ended")
    if not officers.can_end(auth, t, pos, user):
        raise HTTPException(403, "you cannot end terms for %s" % pos.name)
    officers.end_term(db, t, user.id, "stepped down" if t.user_id == user.id else "ended early")
    if t.user_id != user.id:
        notify.officer(db, org, db.get(models.User, t.user_id), "Your term as %s in %s has ended" % (
            pos.name[:80], org.name[:120]), "%s ended your term as %s in %s." % (user.name or user.email, pos.name, org.name))
    audit.log(db, "officer.term_ended_early", user, org_id, client_ip(request), position=pos.name,
              member=t.user_id)
    db.commit()
    return {"ok": True}
