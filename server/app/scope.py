from fastapi import HTTPException
from sqlalchemy import select

from . import models

LEVEL = {"school": 1, "district": 2}


def roles_of(db, user):
    return db.scalars(select(models.AdminRole).where(models.AdminRole.user_id == user.id)).all()


def district_ids(db, user):
    return {r.target_id for r in roles_of(db, user) if r.scope == "district"}


def school_ids(db, user):
    ids = {r.target_id for r in roles_of(db, user) if r.scope == "school"}
    districts = district_ids(db, user)
    if districts:
        ids |= set(db.scalars(select(models.School.id).where(models.School.district_id.in_(districts))).all())
    return ids


def covers_org(db, user, org):
    if user.is_platform_admin:
        return True
    if org.district_id in district_ids(db, user):
        return True
    return bool(org.school_id) and org.school_id in school_ids(db, user)


def scopes(db, user):
    out = []
    for r in roles_of(db, user):
        if r.scope == "district":
            d = db.get(models.District, r.target_id)
            if d is not None:
                out.append({"scope": "district", "id": d.id, "name": d.name, "district": d.name, "role_id": r.id})
        else:
            s = db.get(models.School, r.target_id)
            if s is not None:
                d = db.get(models.District, s.district_id)
                out.append({"scope": "school", "id": s.id, "name": s.name, "district": d.name if d else "",
                            "role_id": r.id})
    return out


def resolve(db, user, scope, target_id):
    if scope not in models.ADMIN_SCOPES:
        raise HTTPException(404, "not found")
    if scope == "district":
        district = db.get(models.District, target_id)
        if district is None or not (user.is_platform_admin or target_id in district_ids(db, user)):
            raise HTTPException(404, "not found")
        schools = db.scalars(select(models.School).where(models.School.district_id == district.id)).all()
        return {"scope": "district", "district": district, "school": None, "schools": schools,
                "school_ids": {s.id for s in schools}, "level": LEVEL["district"] if not user.is_platform_admin else 3}
    school = db.get(models.School, target_id)
    if school is None or not (user.is_platform_admin or target_id in school_ids(db, user)):
        raise HTTPException(404, "not found")
    level = 3 if user.is_platform_admin else (LEVEL["district"] if school.district_id in district_ids(db, user)
                                              else LEVEL["school"])
    return {"scope": "school", "district": db.get(models.District, school.district_id), "school": school,
            "schools": [school], "school_ids": {school.id}, "level": level}


def orgs_in(db, ctx):
    stmt = select(models.Organization)
    if ctx["scope"] == "district":
        stmt = stmt.where(models.Organization.district_id == ctx["district"].id)
    else:
        stmt = stmt.where(models.Organization.school_id == ctx["school"].id)
    return db.scalars(stmt.order_by(models.Organization.name)).all()


def staff_domains_for(db, scope, target):
    if scope == "school":
        return set(target.staff_domains or [])
    domains = set(target.staff_domains or [])
    for s in db.scalars(select(models.School).where(models.School.district_id == target.id)):
        domains |= set(s.staff_domains or [])
    return domains


def staff_proof(db, user, scope, target):
    domains = staff_domains_for(db, scope, target)
    if not domains:
        return None
    return db.scalar(select(models.SchoolEmail).where(models.SchoolEmail.user_id == user.id,
                                                      models.SchoolEmail.verified_at.is_not(None),
                                                      models.SchoolEmail.domain.in_(domains)))


def can_grant(db, granter, scope, target):
    if granter.is_platform_admin:
        return True
    if scope == "school":
        return target.district_id in district_ids(db, granter)
    return False
