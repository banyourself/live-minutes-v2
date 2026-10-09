import time

from fastapi import HTTPException
from sqlalchemy import or_, select

from . import audit, models, notify, scope

LABELS = {
    "assign_officers": "Assign positions ranked below their own",
    "remove_officers": "End terms for positions ranked below their own",
    "edit_permissions": "Edit positions and what each one can do",
    "review_minutes": "Review minutes before they are approved",
    "manage_funding": "Manage funding requests",
    "delete_organization": "Delete the organization (only where college or district IT allows it)",
}
TOP = 10 ** 6
MAX_RANK = 999

DEFAULTS = [
    ("Advisor", 100, "owner", list(models.POSITION_PERMISSIONS), ["faculty", "staff"], 0),
    ("President", 90, "owner", ["assign_officers", "remove_officers"], [], 1),
    ("Vice President", 80, "secretary", ["assign_officers"], [], 0),
    ("Secretary", 70, "secretary", [], [], 0),
    ("Treasurer", 70, "member", ["manage_funding"], [], 0),
    ("Officer", 50, "member", [], [], 0),
]


def org_cfg(org):
    cfg = org.settings or {}
    return {"owners_manage_officers": bool(cfg.get("owners_manage_officers", True)),
            "require_review": bool(cfg.get("require_review", True))}


def positions(db, org):
    rows = db.scalars(select(models.Position).where(models.Position.org_id == org.id)
                      .order_by(models.Position.rank.desc(), models.Position.name)).all()
    if rows or (org.settings or {}).get("positions_seeded"):
        return list(rows)
    for name, rank, access, perms, types, most in DEFAULTS:
        db.add(models.Position(org_id=org.id, name=name, rank=rank, access=access, permissions=perms,
                               account_types=types, max_holders=most))
    org.settings = dict(org.settings or {}, positions_seeded=True)
    db.flush()
    return positions(db, org)


def term_state(t, at=None):
    at = time.time() if at is None else at
    if t.ended_at is not None or (t.ends_at is not None and t.ends_at <= at):
        return "ended"
    return "active" if t.starts_at <= at else "upcoming"


def active_query(org_id, at=None):
    at = time.time() if at is None else at
    return (select(models.PositionTerm, models.Position)
            .join(models.Position, models.Position.id == models.PositionTerm.position_id)
            .where(models.PositionTerm.org_id == org_id, models.PositionTerm.ended_at.is_(None),
                   models.PositionTerm.starts_at <= at,
                   or_(models.PositionTerm.ends_at.is_(None), models.PositionTerm.ends_at > at)))


def held(db, org_id, user_id):
    return db.execute(active_query(org_id).where(models.PositionTerm.user_id == user_id)).all()


def effective_role(db, membership):
    best = membership.role
    for _, p in held(db, membership.org_id, membership.user_id):
        if models.ROLE_RANK.get(p.access, 0) > models.ROLE_RANK[best]:
            best = p.access
    return best


def holders_with(db, org_id, permission):
    return [(t, p) for t, p in db.execute(active_query(org_id)).all() if permission in (p.permissions or [])]


def review_required(db, org):
    return org_cfg(org)["require_review"] and bool(holders_with(db, org.id, "review_minutes"))


class Authority:
    def __init__(self, ranks, above, owner, access):
        self.ranks = ranks
        self.above = above
        self.owner = owner
        self.access = access

    def rank(self, permission):
        return TOP if self.above else self.ranks.get(permission, -1)

    def has(self, permission):
        return self.above or permission in self.ranks

    def permissions(self):
        return set(models.POSITION_PERMISSIONS) if self.above else set(self.ranks)


def advisor_floor(rows):
    ranks = [p.rank for p in rows if "edit_permissions" in (p.permissions or [])]
    return min(ranks) if ranks else TOP


def membership(db, org_id, user_id):
    return db.scalar(select(models.Membership).where(models.Membership.org_id == org_id,
                                                     models.Membership.user_id == user_id))


def authority(db, user, org, rows=None):
    if user.is_platform_admin or scope.covers_org(db, user, org):
        return Authority({}, True, True, "owner")
    m = membership(db, org.id, user.id)
    if m is None:
        return Authority({}, False, False, "")
    ranks = {}
    for _, p in held(db, org.id, user.id):
        for perm in p.permissions or []:
            ranks[perm] = max(ranks.get(perm, -1), p.rank)
    owner = m.role == "owner"
    if owner and org_cfg(org)["owners_manage_officers"]:
        floor = advisor_floor(rows if rows is not None else db.scalars(
            select(models.Position).where(models.Position.org_id == org.id)).all())
        for perm in ("assign_officers", "remove_officers"):
            ranks[perm] = max(ranks.get(perm, -1), floor)
    return Authority(ranks, False, owner, effective_role(db, m))


def can_assign(db, auth, org, pos):
    if pos.rank < auth.rank("assign_officers"):
        return True
    return auth.owner and "edit_permissions" in (pos.permissions or []) and not holders_with(db, org.id, "edit_permissions")


def can_end(auth, term, pos, user):
    return term.user_id == user.id or pos.rank < auth.rank("remove_officers")


def can_edit(auth, pos):
    return auth.has("edit_permissions") and pos.rank < auth.rank("edit_permissions")


def need_editor(auth):
    if not auth.has("edit_permissions"):
        raise HTTPException(403, "only advisors, college IT, and district IT can change positions and permissions")


def check_position(auth, name, rank, access, perms, types, most):
    name = " ".join((name or "").split())[:80]
    if len(name) < 2:
        raise HTTPException(400, "enter the position name")
    if not 1 <= rank <= MAX_RANK:
        raise HTTPException(400, "rank must be between 1 and %d" % MAX_RANK)
    if rank >= auth.rank("edit_permissions"):
        raise HTTPException(403, "you can only set ranks below your own position")
    if access not in models.ROLES:
        raise HTTPException(400, "unknown access level")
    if models.ROLE_RANK[access] > models.ROLE_RANK.get(auth.access, -1):
        raise HTTPException(403, "you cannot give a position more access than you have")
    perms = sorted(set(perms or []))
    if any(p not in models.POSITION_PERMISSIONS for p in perms):
        raise HTTPException(400, "unknown permission")
    if not set(perms) <= auth.permissions():
        raise HTTPException(403, "you can only give permissions you have yourself")
    types = sorted(set(types or []))
    if any(t not in models.ACCOUNT_TYPES for t in types):
        raise HTTPException(400, "unknown account type")
    if not 0 <= most <= 500:
        raise HTTPException(400, "the holder limit must be between 0 (no limit) and 500")
    return name, rank, access, perms, types, most


def overlapping(db, pos_id, start, end, skip_id=None):
    q = select(models.PositionTerm).where(models.PositionTerm.position_id == pos_id,
                                          models.PositionTerm.ended_at.is_(None),
                                          or_(models.PositionTerm.ends_at.is_(None),
                                              models.PositionTerm.ends_at > start))
    if end is not None:
        q = q.where(models.PositionTerm.starts_at < end)
    rows = db.scalars(q).all()
    return [t for t in rows if t.id != skip_id]


def check_holder(db, org, pos, who):
    if pos.account_types and who.account_type not in pos.account_types:
        raise HTTPException(400, "%s is only for %s accounts; %s is set up as %s" % (
            pos.name, " or ".join(t.title() for t in pos.account_types), who.name or who.email,
            (who.account_type or "no account type").title()))
    if pos.account_types and org.school_id:
        from .routes.directory import verified_for_school
        school = db.get(models.School, org.school_id)
        if school is not None and verified_for_school(db, who, school) is None:
            raise HTTPException(400, "%s needs a confirmed %s email at %s before holding %s" % (
                who.name or who.email, "work" if who.account_type in models.STAFF_TYPES else "student",
                school.name, pos.name))


def check_window(db, pos, user_id, start, end, skip_id=None):
    now = time.time()
    if skip_id is None and (start < now - 86400 * 366 or start > now + 86400 * 366 * 2):
        raise HTTPException(400, "the term must start within two years")
    if end is not None and (end <= start or end > start + 86400 * 366 * 10):
        raise HTTPException(400, "the term must end after it starts and within ten years")
    if end is not None and end <= now:
        raise HTTPException(400, "the term must end in the future")
    rows = overlapping(db, pos.id, start, end, skip_id)
    if any(t.user_id == user_id for t in rows):
        raise HTTPException(409, "this person already holds %s for those dates" % pos.name)
    if pos.max_holders and len(rows) >= pos.max_holders:
        raise HTTPException(409, "%s already has %d holder%s for those dates; end or shorten a term first" % (
            pos.name, pos.max_holders, "" if pos.max_holders == 1 else "s"))


def end_term(db, term, actor_id, reason, at=None):
    term.ended_at = time.time() if at is None else at
    term.ended_by = actor_id or ""
    term.end_reason = reason[:40]


def end_all_for(db, org_id, user_id, actor_id, reason):
    rows = db.scalars(select(models.PositionTerm).where(models.PositionTerm.org_id == org_id,
                                                        models.PositionTerm.user_id == user_id,
                                                        models.PositionTerm.ended_at.is_(None))).all()
    for t in rows:
        end_term(db, t, actor_id, reason)
    return len(rows)


def owner_count(db, org_id):
    return len(db.scalars(select(models.Membership.id).where(models.Membership.org_id == org_id,
                                                             models.Membership.role == "owner")).all())


def expire(db, at=None):
    at = time.time() if at is None else at
    rows = db.execute(select(models.PositionTerm, models.Position, models.Organization)
                      .join(models.Position, models.Position.id == models.PositionTerm.position_id)
                      .join(models.Organization, models.Organization.id == models.PositionTerm.org_id)
                      .where(models.PositionTerm.ended_at.is_(None), models.PositionTerm.ends_at.is_not(None),
                             models.PositionTerm.ends_at <= at)).all()
    for t, p, org in rows:
        end_term(db, t, "", "term ended", t.ends_at)
        who = db.get(models.User, t.user_id)
        removed = False
        if t.remove_at_end:
            m = membership(db, org.id, t.user_id)
            others = [x for x, _ in held(db, org.id, t.user_id) if x.id != t.id]
            if m is not None and not others and not (m.role == "owner" and owner_count(db, org.id) <= 1):
                db.delete(m)
                end_all_for(db, org.id, t.user_id, "", "term ended")
                removed = True
        audit.log(db, "officer.term_ended", None, org.id, "", position=p.name, member=t.user_id,
                  removed=removed)
        if who is not None:
            notify.officer(db, org, who, "Your term as %s in %s has ended" % (p.name[:80], org.name[:120]),
                           "Your term as %s in %s ended on Live Minutes.%s" % (
                               p.name, org.name, " You were also removed from the organization, as set when the "
                               "term was assigned." if removed else ""))
    return len(rows)
