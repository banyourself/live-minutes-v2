import re
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit, colleges, mailer, models, names, personal, ratelimit, scope, validation
from ..db import get_db
from ..deps import client_ip, current_user, platform_admin, require_role
from ..security import token_hash
from ..settings import settings

router = APIRouter(tags=["directory"])
DOMAIN = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
CODE_MINUTES = 10
MAX_CODE_TRIES = 5


class EmailStart(BaseModel):
    email: str
    school_id: str = ""


class EmailConfirm(BaseModel):
    email: str
    code: str


class JoinIn(BaseModel):
    message: str = ""


class DecideIn(BaseModel):
    role: str = "member"
    note: str = ""


class SchoolRequestIn(BaseModel):
    district_id: str = ""
    district_name: str = ""
    school_name: str
    org_name: str
    school_email: str


class SchoolIn(BaseModel):
    district_id: str = ""
    district_name: str = ""
    name: str
    domains: list[str]
    staff_domains: list[str] = []


class SchoolPatch(BaseModel):
    name: str | None = None
    domains: list[str] | None = None
    staff_domains: list[str] | None = None
    active: bool | None = None


class DistrictPatch(BaseModel):
    name: str | None = None
    staff_domains: list[str] | None = None


class ApproveIn(BaseModel):
    domains: list[str] = []
    staff_domains: list[str] = []
    district_id: str = ""
    school_id: str = ""
    district_name: str = ""
    school_name: str = ""
    org_name: str = ""
    allow_duplicate: bool = False


KIND_LABEL = {"org": "organization", "school": "college", "district": "district"}
TYPE_WORD = {"student": "student", "faculty": "work", "staff": "work", "it": "work"}


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:110] or "school"


def clean_name(value, label, limit=200):
    value = " ".join((value or "").split())[:limit]
    if len(value) < 2:
        raise HTTPException(400, "enter the %s" % label)
    return value


def clean_domains(values):
    out = []
    for raw in values or []:
        d = str(raw).strip().lower().lstrip("@")
        if not d:
            continue
        if not DOMAIN.match(d):
            raise HTTPException(400, "%s is not a valid email domain" % d)
        if d in validation.FREE_PROVIDERS:
            raise HTTPException(400, "%s is a personal email provider, not a school domain" % d)
        if d not in out:
            out.append(d)
    if not out:
        raise HTTPException(400, "add at least one school email domain")
    return out[:10]


def clean_staff(values):
    return clean_domains(values) if any(str(v).strip() for v in values or []) else []


def expected_domains(school, account_type):
    staff = set(school.staff_domains or [])
    members = set(school.email_domains or [])
    if account_type in models.STAFF_TYPES:
        return sorted(staff)
    return sorted(members - staff) or sorted(members)


def category_ok(school, domain, account_type):
    return domain in expected_domains(school, account_type)


def need_type(user):
    if user.account_type not in models.ACCOUNT_TYPES:
        raise HTTPException(400, "choose whether you are a student, faculty, staff, or IT under My account first")
    return user.account_type


def verified_for_school(db, user, school):
    rows = db.scalars(select(models.SchoolEmail).where(models.SchoolEmail.user_id == user.id,
                                                       models.SchoolEmail.verified_at.is_not(None))).all()
    kind = user.account_type or "student"
    return next((r for r in rows if category_ok(school, r.domain, kind)), None)


def verified_email(db, user, email):
    return db.scalar(select(models.SchoolEmail).where(models.SchoolEmail.user_id == user.id,
                                                      models.SchoolEmail.email == email.strip().lower(),
                                                      models.SchoolEmail.verified_at.is_not(None)))


def active_school(db, school_id):
    school = db.get(models.School, school_id or "")
    if school is None or not school.active:
        raise HTTPException(404, "school not found")
    return school


def owners_of(db, org_id):
    return db.scalars(select(models.User).join(models.Membership, models.Membership.user_id == models.User.id)
                      .where(models.Membership.org_id == org_id, models.Membership.role == "owner")).all()


def school_payload(school, orgs=None, roles=None, pending=None):
    out = {"id": school.id, "name": school.name, "domains": school.email_domains or [],
           "staff_domains": school.staff_domains or [], "active": school.active}
    if orgs is not None:
        out["orgs"] = [{"id": o.id, "name": o.name, "my_role": (roles or {}).get(o.id),
                        "pending": o.id in (pending or set())} for o in orgs]
    return out


@router.get("/api/directory")
def directory(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    schools = db.scalars(select(models.School).where(models.School.active.is_(True))
                         .order_by(models.School.name)).all()
    orgs = db.scalars(select(models.Organization).where(models.Organization.school_id.is_not(None))
                      .order_by(models.Organization.name)).all()
    by_school = {}
    for o in orgs:
        by_school.setdefault(o.school_id, []).append(o)
    roles = dict(db.execute(select(models.Membership.org_id, models.Membership.role)
                            .where(models.Membership.user_id == user.id)).all())
    pending = set(db.scalars(select(models.JoinRequest.org_id).where(models.JoinRequest.user_id == user.id,
                                                                     models.JoinRequest.status == "pending")).all())
    districts = {}
    for s in schools:
        districts.setdefault(s.district_id, []).append(school_payload(s, by_school.get(s.id, []), roles, pending))
    rows = db.scalars(select(models.District).where(models.District.id.in_(list(districts)))
                      .order_by(models.District.name)).all() if districts else []
    return {"districts": [{"id": d.id, "name": d.name, "schools": districts[d.id]} for d in rows]}


@router.get("/api/me/school-emails")
def my_school_emails(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(models.SchoolEmail).where(models.SchoolEmail.user_id == user.id)
                      .order_by(models.SchoolEmail.created_at)).all()
    return {"emails": [{"id": r.id, "email": r.email, "domain": r.domain, "verified": r.verified_at is not None}
                       for r in rows]}


@router.post("/api/school-emails")
def start_school_email(body: EmailStart, request: Request, user: models.User = Depends(current_user),
                       db: Session = Depends(get_db)):
    ratelimit.hit("school-code-user:" + user.id, 6, 3600, "you have asked for several codes; wait an hour")
    email = validation.clean_email(body.email)
    domain = validation.email_domain(email)
    if validation.is_free_provider(email):
        raise HTTPException(400, "use your school email address here, not a personal one")
    if body.school_id:
        kind = need_type(user)
        school = active_school(db, body.school_id)
        allowed = expected_domains(school, kind)
        if domain not in allowed:
            if not allowed:
                raise HTTPException(400, "%s has no %s email domains set up yet; ask its IT staff or the platform owner"
                                    % (school.name, TYPE_WORD[kind]))
            raise HTTPException(400, "%s %s emails end in %s" % (
                school.name, TYPE_WORD[kind], " or ".join("@" + d for d in allowed)))
    row = db.scalar(select(models.SchoolEmail).where(models.SchoolEmail.email == email))
    if row is not None and row.verified_at is not None:
        if row.user_id == user.id:
            return {"status": "verified", "email": email, "id": row.id}
        raise HTTPException(409, "this school email is already verified on another Live Minutes account")
    ratelimit.hit("school-code-email:" + email, 3, 3600, "a code was sent to this address recently; check your inbox")
    code = "%06d" % secrets.randbelow(1000000)
    if row is None:
        row = models.SchoolEmail(user_id=user.id, email=email, domain=domain)
        db.add(row)
    row.user_id, row.domain = user.id, domain
    row.code_hash = token_hash("school:%s:%s" % (email, code))
    row.code_expires_at, row.attempts = time.time() + CODE_MINUTES * 60, 0
    mailer.queue(db, email, "Your Live Minutes school verification code",
                 "Your code is %s\n\nEnter it on the organization page to confirm this school email. It works "
                 "for %d minutes. If you did not ask for it, ignore this email." % (code, CODE_MINUTES))
    audit.log(db, "school_email.code_sent", user, ip=client_ip(request), email=email)
    db.commit()
    return {"status": "code_sent", "email": email}


@router.post("/api/school-emails/confirm")
def confirm_school_email(body: EmailConfirm, request: Request, user: models.User = Depends(current_user),
                         db: Session = Depends(get_db)):
    ratelimit.hit("school-confirm:" + user.id, 20, 3600)
    email = (body.email or "").strip().lower()
    row = db.scalar(select(models.SchoolEmail).where(models.SchoolEmail.email == email,
                                                     models.SchoolEmail.user_id == user.id))
    if row is None or not row.code_hash or row.code_expires_at < time.time():
        raise HTTPException(400, "this code has expired; send a new one")
    if row.attempts >= MAX_CODE_TRIES:
        raise HTTPException(400, "too many wrong codes; send a new one")
    row.attempts += 1
    code = re.sub(r"\D", "", body.code or "")
    if not secrets.compare_digest(row.code_hash, token_hash("school:%s:%s" % (email, code))):
        db.commit()
        raise HTTPException(400, "that code is not right; check the newest email")
    row.verified_at, row.code_hash = time.time(), ""
    audit.log(db, "school_email.verified", user, ip=client_ip(request), email=email)
    db.commit()
    return {"status": "verified", "email": email, "id": row.id}


@router.delete("/api/school-emails/{email_id}")
def remove_school_email(email_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(models.SchoolEmail, email_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "email not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/api/orgs/{org_id}/join-requests")
def request_join(org_id: str, body: JoinIn, request: Request, user: models.User = Depends(current_user),
                 db: Session = Depends(get_db)):
    org = db.get(models.Organization, org_id)
    if org is None or not org.school_id:
        raise HTTPException(404, "organization not found")
    if db.scalar(select(models.Membership).where(models.Membership.user_id == user.id,
                                                 models.Membership.org_id == org_id)) is not None:
        raise HTTPException(400, "you are already a member of this organization")
    school = db.get(models.School, org.school_id)
    kind = need_type(user)
    proof = verified_for_school(db, user, school) if school else None
    if proof is None:
        raise HTTPException(403, "confirm your %s %s email first" % (school.name if school else "school", TYPE_WORD[kind]))
    ratelimit.hit("join:" + user.id, 20, 86400)
    jr = db.scalar(select(models.JoinRequest).where(models.JoinRequest.org_id == org_id,
                                                    models.JoinRequest.user_id == user.id))
    if jr is None:
        jr = models.JoinRequest(org_id=org_id, user_id=user.id, school_email=proof.email)
        db.add(jr)
    elif jr.status == "pending":
        return {"status": "pending", "id": jr.id}
    jr.status, jr.school_email, jr.message = "pending", proof.email, body.message.strip()[:500]
    jr.created_at, jr.decided_by, jr.decided_at = time.time(), None, None
    for owner in owners_of(db, org_id):
        mailer.queue(db, owner.email, "%s asked to join %s" % (user.name or user.email, org.name[:120]),
                     "%s (%s, verified %s) asked to join %s on Live Minutes.\n\nReview it under Settings, "
                     "Members: %s/settings" % (user.name or user.email, user.email, proof.email, org.name,
                                               settings.public_url))
    audit.log(db, "join.requested", user, org_id, client_ip(request), school_email=proof.email)
    db.commit()
    return {"status": "pending", "id": jr.id}


@router.get("/api/orgs/{org_id}/join-requests")
def list_join_requests(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, org_id, "owner")
    rows = db.execute(select(models.JoinRequest, models.User)
                      .join(models.User, models.User.id == models.JoinRequest.user_id)
                      .where(models.JoinRequest.org_id == org_id, models.JoinRequest.status == "pending")
                      .order_by(models.JoinRequest.created_at)).all()
    return {"requests": [{"id": j.id, "name": u.name, "email": u.email, "school_email": j.school_email,
                          "message": j.message, "created_at": j.created_at} for j, u in rows]}


def _pending_join(db, org_id, request_id):
    jr = db.get(models.JoinRequest, request_id)
    if jr is None or jr.org_id != org_id or jr.status != "pending":
        raise HTTPException(404, "request not found")
    return jr


@router.post("/api/orgs/{org_id}/join-requests/{request_id}/approve")
def approve_join(org_id: str, request_id: str, body: DecideIn, request: Request,
                 user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "owner")
    if body.role not in models.ROLES:
        raise HTTPException(400, "unknown role")
    jr = _pending_join(db, org_id, request_id)
    if db.scalar(select(models.Membership).where(models.Membership.user_id == jr.user_id,
                                                 models.Membership.org_id == org_id)) is None:
        db.add(models.Membership(user_id=jr.user_id, org_id=org_id, role=body.role))
    jr.status, jr.decided_by, jr.decided_at = "approved", user.id, time.time()
    member = db.get(models.User, jr.user_id)
    mailer.queue(db, member.email, "You joined %s on Live Minutes" % org.name[:120],
                 "Your request to join %s was approved. Sign in at %s" % (org.name, settings.public_url))
    audit.log(db, "join.approved", user, org_id, client_ip(request), member=jr.user_id, role=body.role)
    db.commit()
    return {"ok": True}


@router.post("/api/orgs/{org_id}/join-requests/{request_id}/deny")
def deny_join(org_id: str, request_id: str, request: Request, user: models.User = Depends(current_user),
              db: Session = Depends(get_db)):
    require_role(db, user, org_id, "owner")
    jr = _pending_join(db, org_id, request_id)
    jr.status, jr.decided_by, jr.decided_at = "denied", user.id, time.time()
    audit.log(db, "join.denied", user, org_id, client_ip(request), member=jr.user_id)
    db.commit()
    return {"ok": True}


@router.get("/api/me/requests")
def my_requests(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    since = time.time() - 30 * 86400
    joins = db.execute(select(models.JoinRequest, models.Organization)
                       .join(models.Organization, models.Organization.id == models.JoinRequest.org_id)
                       .where(models.JoinRequest.user_id == user.id, models.JoinRequest.created_at > since)
                       .order_by(models.JoinRequest.created_at.desc())).all()
    schools = db.scalars(select(models.SchoolRequest).where(models.SchoolRequest.user_id == user.id,
                                                            models.SchoolRequest.created_at > since)
                         .order_by(models.SchoolRequest.created_at.desc())).all()
    return {"joins": [{"id": j.id, "org": o.name, "school": o.school, "status": j.status, "created_at": j.created_at}
                      for j, o in joins],
            "schools": [{"id": s.id, "kind": s.kind, "school": s.school_name, "district": s.district_name,
                         "org": s.org_name, "status": s.status, "note": s.note, "created_at": s.created_at}
                        for s in schools]}


@router.delete("/api/me/join-requests/{request_id}")
def cancel_join(request_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    jr = db.get(models.JoinRequest, request_id)
    if jr is None or jr.user_id != user.id or jr.status != "pending":
        raise HTTPException(404, "request not found")
    db.delete(jr)
    db.commit()
    return {"ok": True}


def approvers(db, kind, district_id, school_id):
    people = {u.id: u for u in db.scalars(select(models.User).where(models.User.is_platform_admin.is_(True)))}
    roles = []
    if district_id and kind in ("org", "school"):
        roles += db.scalars(select(models.AdminRole).where(models.AdminRole.scope == "district",
                                                           models.AdminRole.target_id == district_id)).all()
    if school_id and kind == "org":
        roles += db.scalars(select(models.AdminRole).where(models.AdminRole.scope == "school",
                                                           models.AdminRole.target_id == school_id)).all()
    for r in roles:
        u = db.get(models.User, r.user_id)
        if u is not None:
            people[u.id] = u
    return list(people.values())


def open_request(db, request, user, kind, district, school, district_name, school_name, org_name, proof):
    pending = db.scalar(select(models.SchoolRequest).where(models.SchoolRequest.status == "pending",
                                                           func.lower(models.SchoolRequest.org_name) == org_name.lower(),
                                                           func.lower(models.SchoolRequest.school_name) == school_name.lower()))
    if pending is not None:
        raise HTTPException(409, "a request for %s at %s is already waiting for approval" % (org_name, school_name))
    sr = models.SchoolRequest(kind=kind, user_id=user.id, district_id=district.id if district else None,
                              school_id=school.id if school else None, district_name=district_name,
                              school_name=school_name, org_name=org_name, school_email=proof.email if proof else "")
    db.add(sr)
    what = {"org": "the organization %s at %s" % (org_name, school_name),
            "school": "the college %s in %s, with the organization %s" % (school_name, district_name, org_name),
            "district": "the district %s with %s and the organization %s" % (district_name, school_name, org_name)}[kind]
    for person in approvers(db, kind, district.id if district else None, school.id if school else None):
        mailer.queue(db, person.email, "New %s request on Live Minutes" % KIND_LABEL[kind],
                     "%s (%s, %s) asked to add %s.%s\n\nReview it at %s/%s" % (
                         user.name or user.email, user.email, user.account_type or "no account type",
                         what, (" They confirmed " + proof.email + ".") if proof else "", settings.public_url,
                         "admin" if person.is_platform_admin else "manage"))
    audit.log(db, kind + ".requested", user, ip=client_ip(request), district=district_name, school=school_name,
              org=org_name)
    db.commit()
    return sr


@router.post("/api/school-requests")
def request_school(body: SchoolRequestIn, request: Request, user: models.User = Depends(current_user),
                   db: Session = Depends(get_db)):
    ratelimit.hit("school-request:" + user.id, 5, 86400)
    need_type(user)
    proof = verified_email(db, user, body.school_email)
    if proof is None:
        raise HTTPException(400, "confirm that school email first")
    district = db.get(models.District, body.district_id) if body.district_id else None
    if body.district_id and district is None:
        raise HTTPException(404, "district not found")
    district_name = district.name if district else clean_name(body.district_name, "school district name")
    sr = open_request(db, request, user, "school" if district else "district", district, None, district_name,
                      clean_name(body.school_name, "school name"), clean_name(body.org_name, "organization name"), proof)
    return {"status": "pending", "id": sr.id}


def possible_duplicates(db, sr):
    if sr.kind == "district":
        return names.similar(db.scalars(select(models.District)).all(), sr.district_name)
    if sr.kind == "school":
        rows = db.scalars(select(models.School).where(models.School.district_id == sr.district_id)).all()
        return names.similar(rows, sr.school_name)
    rows = db.scalars(select(models.Organization).where(models.Organization.school_id == sr.school_id)).all()
    return names.similar(rows, sr.org_name)


def college_check(r):
    if r.kind == "org":
        return None
    match = colleges.best(r.school_name)
    if match is None:
        return None
    domain = validation.email_domain(r.school_email) if r.school_email else ""
    return dict(match, email_matches=colleges.domain_known(domain, match["domains"]))


def request_rows(db, rows):
    return [{"id": r.id, "kind": r.kind, "status": r.status, "district": r.district_name, "district_id": r.district_id,
             "school": r.school_name, "school_id": r.school_id, "org": r.org_name, "school_email": r.school_email,
             "domain": validation.email_domain(r.school_email) if r.school_email else "", "user": u.email,
             "name": u.name, "account_type": u.account_type, "note": r.note, "created_at": r.created_at,
             "possible_duplicates": possible_duplicates(db, r) if r.status == "pending" else [],
             "college": college_check(r) if r.status == "pending" else None} for r, u in rows]


@router.get("/api/admin/school-requests")
def admin_school_requests(user: models.User = Depends(platform_admin), db: Session = Depends(get_db)):
    rows = db.execute(select(models.SchoolRequest, models.User)
                      .join(models.User, models.User.id == models.SchoolRequest.user_id)
                      .order_by(models.SchoolRequest.status != "pending", models.SchoolRequest.created_at.desc())
                      .limit(200)).all()
    return {"requests": request_rows(db, rows)}


@router.get("/api/directory/colleges")
def college_names(q: str = "", user: models.User = Depends(current_user)):
    ratelimit.hit("college-search:" + user.id, 120, 600)
    return {"matches": colleges.search(q[:120])}


@router.get("/api/directory/suggest")
def suggest(kind: str, name: str, parent_id: str = "", user: models.User = Depends(current_user),
            db: Session = Depends(get_db)):
    if len(name.strip()) < 2:
        return {"matches": []}
    if kind == "district":
        rows = db.scalars(select(models.District).where(models.District.slug != personal.SLUG)).all()
    elif kind == "school":
        rows = db.scalars(select(models.School).where(models.School.district_id == parent_id,
                                                      models.School.active.is_(True))).all()
    elif kind == "org":
        rows = db.scalars(select(models.Organization).where(models.Organization.school_id == parent_id)).all()
    else:
        raise HTTPException(400, "unknown kind")
    return {"matches": names.similar(rows, name)[:5]}


def find_or_create_school(db, district, name, domains):
    slug = slugify(name)
    school = db.scalar(select(models.School).where(models.School.district_id == district.id,
                                                   models.School.slug == slug))
    if school is None:
        school = models.School(district_id=district.id, name=name, slug=slug, email_domains=domains)
        db.add(school)
        db.flush()
    else:
        school.email_domains = list(dict.fromkeys((school.email_domains or []) + domains))
        school.active = True
    return school


def find_or_create_district(db, name):
    slug = slugify(name)[:80]
    district = db.scalar(select(models.District).where(models.District.slug == slug))
    if district is None:
        district = models.District(name=name, slug=slug, allowed_domains=[])
        db.add(district)
        db.flush()
    return district


def org_name_taken(db, school_id, name):
    return db.scalar(select(models.Organization).where(models.Organization.school_id == school_id,
                                                       func.lower(models.Organization.name) == name.lower())) is not None


def can_decide(db, user, sr):
    if user.is_platform_admin:
        return True
    if sr.kind == "org":
        return bool(sr.school_id) and sr.school_id in scope.school_ids(db, user)
    if sr.kind == "school":
        return bool(sr.district_id) and sr.district_id in scope.district_ids(db, user)
    return False


def duplicate_guard(found, label, allow):
    if found and not allow:
        raise HTTPException(409, "this %s looks like %s, which already exists; choose it instead, or confirm it is "
                                 "different" % (label, " or ".join(f["name"] for f in found)))


def approve_school_request(db, request, user, sr, body):
    if not can_decide(db, user, sr):
        raise HTTPException(403, "you cannot approve this request")
    requester = db.get(models.User, sr.user_id)
    school_id = body.school_id or (sr.school_id if sr.kind == "org" else "")
    if school_id:
        school = active_school(db, school_id)
        if not user.is_platform_admin and school.id not in scope.school_ids(db, user):
            raise HTTPException(403, "that college is outside your area")
        district = db.get(models.District, school.district_id)
    else:
        district_id = body.district_id or sr.district_id or ""
        if district_id:
            district = db.get(models.District, district_id)
            if district is None:
                raise HTTPException(404, "district not found")
            if not user.is_platform_admin and district.id not in scope.district_ids(db, user):
                raise HTTPException(403, "that district is outside your area")
        else:
            if not user.is_platform_admin:
                raise HTTPException(403, "only the platform owner can add a district")
            district_name = clean_name(body.district_name or sr.district_name, "district name")
            duplicate_guard(names.similar(db.scalars(select(models.District)).all(), district_name), "district",
                            body.allow_duplicate)
            district = find_or_create_district(db, district_name)
        domain = validation.email_domain(sr.school_email) if sr.school_email else ""
        domains = clean_domains(body.domains or ([domain] if domain else []))
        school_name = clean_name(body.school_name or sr.school_name, "school name")
        siblings = db.scalars(select(models.School).where(models.School.district_id == district.id)).all()
        duplicate_guard(names.similar(siblings, school_name), "college", body.allow_duplicate)
        school = find_or_create_school(db, district, school_name, domains)
        if body.staff_domains:
            school.staff_domains = clean_staff(body.staff_domains)
    org_name = clean_name(body.org_name or sr.org_name, "organization name")
    if org_name_taken(db, school.id, org_name):
        raise HTTPException(409, "%s already has an organization named %s; ask the requester to request to join"
                            % (school.name, org_name))
    peers = db.scalars(select(models.Organization).where(models.Organization.school_id == school.id)).all()
    duplicate_guard(names.similar(peers, org_name), "organization", body.allow_duplicate)
    org = models.Organization(district_id=district.id, school_id=school.id, school=school.name, name=org_name,
                              settings={})
    db.add(org)
    db.flush()
    db.add(models.Membership(user_id=sr.user_id, org_id=org.id, role="owner"))
    sr.status, sr.org_id, sr.decided_by, sr.decided_at = "approved", org.id, user.id, time.time()
    sr.school_id, sr.district_id = school.id, district.id
    mailer.queue(db, requester.email, "%s is ready on Live Minutes" % org_name[:120],
                 "Your request was approved. %s at %s is set up and you are its owner. Sign in at %s"
                 % (org_name, school.name, settings.public_url))
    audit.log(db, sr.kind + ".approved", user, org.id, client_ip(request), school=school.name, district=district.name)
    db.commit()
    return {"ok": True, "org_id": org.id, "school_id": school.id}


def reject_school_request(db, request, user, sr, body):
    if not can_decide(db, user, sr):
        raise HTTPException(403, "you cannot decide this request")
    sr.status, sr.note, sr.decided_by, sr.decided_at = "rejected", body.note.strip()[:500], user.id, time.time()
    requester = db.get(models.User, sr.user_id)
    mailer.queue(db, requester.email, "Your Live Minutes school request",
                 "Your request to add %s was not approved.%s" % (
                     sr.org_name if sr.kind == "org" else sr.school_name if sr.kind == "school" else sr.district_name,
                     (" Note: " + sr.note) if sr.note else ""))
    audit.log(db, sr.kind + ".rejected", user, ip=client_ip(request), school=sr.school_name, org=sr.org_name)
    db.commit()
    return {"ok": True}


def pending_request(db, request_id):
    sr = db.get(models.SchoolRequest, request_id)
    if sr is None or sr.status != "pending":
        raise HTTPException(404, "request not found")
    return sr


@router.post("/api/admin/school-requests/{request_id}/approve")
def admin_approve_school(request_id: str, body: ApproveIn, request: Request, user: models.User = Depends(platform_admin),
                         db: Session = Depends(get_db)):
    return approve_school_request(db, request, user, pending_request(db, request_id), body)


@router.post("/api/admin/school-requests/{request_id}/reject")
def admin_reject_school(request_id: str, body: DecideIn, request: Request, user: models.User = Depends(platform_admin),
                        db: Session = Depends(get_db)):
    return reject_school_request(db, request, user, pending_request(db, request_id), body)


@router.get("/api/admin/directory")
def admin_directory(user: models.User = Depends(platform_admin), db: Session = Depends(get_db)):
    districts = db.scalars(select(models.District).order_by(models.District.name)).all()
    schools = db.scalars(select(models.School).order_by(models.School.name)).all()
    counts = dict(db.execute(select(models.Organization.school_id, func.count())
                             .group_by(models.Organization.school_id)).all())
    out = []
    for d in districts:
        rows = [dict(school_payload(s), org_count=counts.get(s.id, 0), staff_domains=s.staff_domains or [])
                for s in schools if s.district_id == d.id]
        out.append({"id": d.id, "name": d.name, "staff_domains": d.staff_domains or [], "schools": rows})
    return {"districts": out}


@router.post("/api/admin/schools")
def admin_add_school(body: SchoolIn, request: Request, user: models.User = Depends(platform_admin),
                     db: Session = Depends(get_db)):
    district = db.get(models.District, body.district_id) if body.district_id else None
    if district is None:
        district = find_or_create_district(db, clean_name(body.district_name, "district name"))
    school = find_or_create_school(db, district, clean_name(body.name, "school name"), clean_domains(body.domains))
    if body.staff_domains:
        school.staff_domains = clean_staff(body.staff_domains)
    audit.log(db, "school.added", user, ip=client_ip(request), school=school.name, domains=school.email_domains)
    db.commit()
    return school_payload(school)


@router.patch("/api/admin/schools/{school_id}")
def admin_edit_school(school_id: str, body: SchoolPatch, request: Request, user: models.User = Depends(platform_admin),
                      db: Session = Depends(get_db)):
    school = db.get(models.School, school_id)
    if school is None:
        raise HTTPException(404, "school not found")
    if body.name is not None:
        school.name = clean_name(body.name, "school name")
    if body.domains is not None:
        school.email_domains = clean_domains(body.domains)
    if body.staff_domains is not None:
        school.staff_domains = clean_staff(body.staff_domains)
    if body.active is not None:
        school.active = body.active
    audit.log(db, "school.edited", user, ip=client_ip(request), school=school.name, domains=school.email_domains,
              staff_domains=school.staff_domains, active=school.active)
    db.commit()
    return dict(school_payload(school), staff_domains=school.staff_domains or [])


@router.patch("/api/admin/districts/{district_id}")
def admin_edit_district(district_id: str, body: DistrictPatch, request: Request,
                        user: models.User = Depends(platform_admin), db: Session = Depends(get_db)):
    district = db.get(models.District, district_id)
    if district is None:
        raise HTTPException(404, "district not found")
    if body.name is not None:
        district.name = clean_name(body.name, "district name")
    if body.staff_domains is not None:
        district.staff_domains = clean_staff(body.staff_domains)
    audit.log(db, "district.edited", user, ip=client_ip(request), district=district.name,
              staff_domains=district.staff_domains)
    db.commit()
    return {"id": district.id, "name": district.name, "staff_domains": district.staff_domains or []}
