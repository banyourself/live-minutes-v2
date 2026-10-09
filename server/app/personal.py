from fastapi import HTTPException
from sqlalchemy import func, select

from . import audit, models, runtime

SLUG = "_personal"
NAME = "Personal workspaces"


def district(db):
    found = db.scalar(select(models.District).where(models.District.slug == SLUG))
    if found is None:
        found = models.District(name=NAME, slug=SLUG, allowed_domains=[], staff_domains=[], settings={"personal": True})
        db.add(found)
        db.flush()
    return found


def is_personal_district(row):
    return row is not None and row.slug == SLUG


def is_personal(db, org_id):
    org = db.get(models.Organization, org_id)
    return org is not None and is_personal_district(db.get(models.District, org.district_id))


def has_workspace(db, user):
    return db.scalar(select(models.Membership.id)
                     .join(models.Organization, models.Organization.id == models.Membership.org_id)
                     .join(models.District, models.District.id == models.Organization.district_id)
                     .where(models.Membership.user_id == user.id, models.District.slug == SLUG)
                     .limit(1)) is not None


def workspace_name(label):
    label = " ".join((label or "").split())[:80]
    return label + "'s meetings" if label else "Personal meetings"


def open_signup():
    return bool(runtime.get("allow_signup") and runtime.get("allow_personal_signup"))


def ensure_workspace(db, user):
    if has_workspace(db, user):
        return None
    org = models.Organization(district_id=district(db).id, school_id=None, school="", name=workspace_name(user.name),
                              settings={})
    db.add(org)
    db.flush()
    db.add(models.Membership(user_id=user.id, org_id=org.id, role="owner"))
    audit.log(db, "org.personal_created", user, org.id)
    return org


def storage_cap():
    return int(runtime.get("personal_storage_mb")) * 1048576


def storage_used(db, org_id, skip=""):
    return int(db.scalar(select(func.coalesce(func.sum(models.Meeting.recording_size), 0))
                         .where(models.Meeting.org_id == org_id, models.Meeting.recording_key != "",
                                models.Meeting.id != skip)) or 0)


def has_room(db, org_id, size, skip=""):
    return not is_personal(db, org_id) or storage_used(db, org_id, skip) + size <= storage_cap()


def check_room(db, org_id, size, skip=""):
    if not has_room(db, org_id, size, skip):
        raise HTTPException(413, "a personal workspace can keep up to %d MB of recordings; delete an older recording "
                                 "to make room" % (storage_cap() // 1048576))
