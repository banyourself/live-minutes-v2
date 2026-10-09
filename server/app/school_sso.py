import re
import time

from fastapi import HTTPException
from sqlalchemy import select

from . import audit, models

GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
DOMAIN = re.compile(r"^(?=.{3,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def config(district):
    cfg = (district.settings or {}).get("sso") or {}
    return {"microsoft_tenants": list(cfg.get("microsoft_tenants") or []),
            "google_domains": list(cfg.get("google_domains") or []),
            "auto_setup": bool(cfg.get("auto_setup", True))}


def clean(tenants, domains, auto_setup):
    t = sorted({x.strip().lower() for x in tenants or [] if x.strip()})
    if any(not GUID.match(x) for x in t):
        raise HTTPException(400, "Microsoft tenant IDs look like 00000000-0000-0000-0000-000000000000; find yours in "
                                 "the Microsoft Entra admin center under Overview")
    d = sorted({x.strip().lower().lstrip("@") for x in domains or [] if x.strip()})
    if any(not DOMAIN.match(x) for x in d):
        raise HTTPException(400, "enter Google Workspace domains like coastline.edu")
    if len(t) > 20 or len(d) > 20:
        raise HTTPException(400, "a district can list up to 20 tenants and 20 domains")
    return {"microsoft_tenants": t, "google_domains": d, "auto_setup": bool(auto_setup)}


def districts(db):
    return [d for d in db.scalars(select(models.District)).all() if (d.settings or {}).get("sso")]


def tenants(db):
    out = set()
    for d in districts(db):
        out.update(config(d)["microsoft_tenants"])
    return sorted(out)


def taken(db, district_id, cfg):
    for d in districts(db):
        if d.id == district_id:
            continue
        other = config(d)
        clash = set(other["microsoft_tenants"]) & set(cfg["microsoft_tenants"]) or \
            set(other["google_domains"]) & set(cfg["google_domains"])
        if clash:
            return d.name, sorted(clash)[0]
    return None


def match(db, info):
    for d in districts(db):
        cfg = config(d)
        if info.get("provider") == "microsoft" and info.get("tid") in cfg["microsoft_tenants"]:
            return d
        if info.get("provider") == "google" and info.get("hd") and info.get("hd") in cfg["google_domains"]:
            return d
    return None


def district_domain(db, district, email):
    if district is None or "@" not in email:
        return False
    domain = email.rsplit("@", 1)[-1]
    schools = db.scalars(select(models.School).where(models.School.district_id == district.id)).all()
    return any(domain in (s.email_domains or []) for s in schools) or domain in (district.staff_domains or [])


def setup(db, district, user, email, provider):
    domain = email.rsplit("@", 1)[-1]
    schools = db.scalars(select(models.School).where(models.School.district_id == district.id,
                                                     models.School.active.is_(True))).all()
    school = next((s for s in schools if domain in (s.email_domains or [])), None)
    if school is None:
        return None
    staff = domain in (school.staff_domains or []) or domain in (district.staff_domains or [])
    if not user.account_type:
        user.account_type = "staff" if staff else "student"
    row = db.scalar(select(models.SchoolEmail).where(models.SchoolEmail.email == email))
    if row is not None and row.verified_at is not None and row.user_id != user.id:
        return None
    if row is None:
        row = models.SchoolEmail(user_id=user.id, email=email, domain=domain)
        db.add(row)
    if row.verified_at is None or row.user_id != user.id:
        row.user_id, row.domain, row.verified_at, row.code_hash = user.id, domain, time.time(), ""
        audit.log(db, "school_email.verified_sso", user, school=school.id, email=email, provider=provider,
                  district=district.id)
    return school
