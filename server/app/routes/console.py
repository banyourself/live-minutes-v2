import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import audit, governance, models, ratelimit, scope
from ..db import get_db
from ..deps import client_ip, current_user, sudo_user
from ..settings import settings
from .auth import send_reset
from ..roles import grant_role, revoke_role, role_rows
from .admin import fail_counts, locked
from .directory import (ApproveIn, DecideIn, SchoolIn, SchoolPatch, approve_school_request, clean_domains,
                        clean_name, clean_staff, find_or_create_school, reject_school_request, request_rows,
                        school_payload)

router = APIRouter(prefix="/api/manage", tags=["it console"])


class GrantIn(BaseModel):
    email: str
    school_id: str = ""


def ctx_for(db, user, scope_name, target_id):
    return scope.resolve(db, user, scope_name, target_id)


def scope_org_ids(db, ctx):
    return [o.id for o in scope.orgs_in(db, ctx)]


def scope_user_ids(db, ctx):
    ids = scope_org_ids(db, ctx)
    if not ids:
        return set()
    return set(db.scalars(select(models.Membership.user_id).where(models.Membership.org_id.in_(ids))).all())


def person_in_scope(db, ctx, user_id):
    if user_id not in scope_user_ids(db, ctx):
        raise HTTPException(404, "person not found")
    return db.get(models.User, user_id)


def need_outranked(db, ctx, person):
    above = person.is_platform_admin or (ctx["scope"] == "school" and db.scalar(
        select(models.AdminRole.id).where(models.AdminRole.user_id == person.id, models.AdminRole.scope == "district")))
    if above:
        raise HTTPException(403, "ask district IT or the platform owner to help this person")


@router.get("/scopes")
def my_scopes(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return {"scopes": scope.scopes(db, user), "platform_owner": user.is_platform_admin}


@router.get("/{scope_name}/{target_id}/overview")
def overview(scope_name: str, target_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = ctx_for(db, user, scope_name, target_id)
    org_ids = scope_org_ids(db, ctx)
    people = scope_user_ids(db, ctx)
    meetings = db.scalar(select(func.count()).select_from(models.Meeting).where(models.Meeting.org_id.in_(org_ids))) if org_ids else 0
    joins = db.scalar(select(func.count()).select_from(models.JoinRequest).where(
        models.JoinRequest.org_id.in_(org_ids), models.JoinRequest.status == "pending")) if org_ids else 0
    schools = len([1 for r, _ in db.execute(scope_requests_stmt(ctx)).all() if r.status == "pending"])
    return {"scope": ctx["scope"], "name": (ctx["school"] or ctx["district"]).name, "district": ctx["district"].name,
            "can_manage_admins": ctx["scope"] == "district" or user.is_platform_admin,
            "counts": {"orgs": len(org_ids), "people": len(people), "meetings": meetings or 0, "join_requests": joins or 0,
                       "school_requests": schools or 0, "schools": len(ctx["schools"])}}


@router.get("/{scope_name}/{target_id}/orgs")
def orgs(scope_name: str, target_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = ctx_for(db, user, scope_name, target_id)
    out = []
    for o in scope.orgs_in(db, ctx):
        owners = db.scalars(select(models.User.email).join(models.Membership, models.Membership.user_id == models.User.id)
                            .where(models.Membership.org_id == o.id, models.Membership.role == "owner")).all()
        out.append({"id": o.id, "name": o.name, "school": o.school, "created_at": o.created_at, "owners": owners,
                    "members": db.scalar(select(func.count()).select_from(models.Membership)
                                         .where(models.Membership.org_id == o.id)) or 0,
                    "meetings": db.scalar(select(func.count()).select_from(models.Meeting)
                                          .where(models.Meeting.org_id == o.id)) or 0})
    return {"orgs": out}


class OrgRulesIn(BaseModel):
    advisors_create_orgs: bool = False
    allow_org_delete: bool = False


def rules_holder(db, ctx):
    return ctx["district"] if ctx["scope"] == "district" else ctx["school"]


@router.get("/{scope_name}/{target_id}/org-rules")
def get_org_rules(scope_name: str, target_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = ctx_for(db, user, scope_name, target_id)
    if ctx["scope"] == "district":
        return governance.org_rules_for(db, None, ctx["district"].id)
    return governance.org_rules_for(db, ctx["school"].id, ctx["district"].id)


@router.put("/{scope_name}/{target_id}/org-rules")
def set_org_rules(scope_name: str, target_id: str, body: OrgRulesIn, request: Request,
                  user: models.User = Depends(sudo_user), db: Session = Depends(get_db)):
    ctx = ctx_for(db, user, scope_name, target_id)
    holder = rules_holder(db, ctx)
    cfg = dict(holder.settings or {})
    cfg["org_rules"] = {"advisors_create_orgs": body.advisors_create_orgs, "allow_org_delete": body.allow_org_delete}
    holder.settings = cfg
    audit.log(db, "it.org_rules", user, ip=client_ip(request), scope=ctx["scope"], scope_id=target_id, **cfg["org_rules"])
    db.commit()
    return cfg["org_rules"]


@router.delete("/{scope_name}/{target_id}/orgs/{org_id}")
def delete_org(scope_name: str, target_id: str, org_id: str, request: Request, confirm: str = "",
               user: models.User = Depends(sudo_user), db: Session = Depends(get_db)):
    ctx = ctx_for(db, user, scope_name, target_id)
    org = next((o for o in scope.orgs_in(db, ctx) if o.id == org_id), None)
    if org is None:
        raise HTTPException(404, "organization not found")
    if confirm.strip().lower() != org.name.strip().lower():
        raise HTTPException(400, "type the organization's name to confirm")
    governance.check_hold(db, org, "delete this organization")
    audit.log(db, "it.delete_org", user, org.id, client_ip(request), name=org.name, scope=ctx["scope"])
    governance.delete_org(db, org)
    db.commit()
    return {"ok": True}


@router.get("/{scope_name}/{target_id}/orgs/{org_id}")
def org_detail(scope_name: str, target_id: str, org_id: str, user: models.User = Depends(current_user),
               db: Session = Depends(get_db)):
    ctx = ctx_for(db, user, scope_name, target_id)
    if org_id not in scope_org_ids(db, ctx):
        raise HTTPException(404, "organization not found")
    o = db.get(models.Organization, org_id)
    members = db.execute(select(models.Membership, models.User).join(models.User, models.User.id == models.Membership.user_id)
                         .where(models.Membership.org_id == o.id).order_by(models.User.email)).all()
    meetings = db.scalars(select(models.Meeting).where(models.Meeting.org_id == o.id)
                          .order_by(models.Meeting.created_at.desc()).limit(100)).all()
    return {"id": o.id, "name": o.name, "school": o.school, "created_at": o.created_at,
            "members": [{"membership_id": m.id, "user_id": u.id, "email": u.email, "name": u.name, "role": m.role}
                        for m, u in members],
            "meetings": [{"id": m.id, "title": m.title, "status": m.status, "created_at": m.created_at} for m in meetings]}


@router.get("/{scope_name}/{target_id}/people")
def people(scope_name: str, target_id: str, q: str = "", user: models.User = Depends(current_user),
           db: Session = Depends(get_db)):
    ctx = ctx_for(db, user, scope_name, target_id)
    org_ids = scope_org_ids(db, ctx)
    if not org_ids:
        return {"people": []}
    rows = db.execute(select(models.User, models.Membership, models.Organization)
                      .join(models.Membership, models.Membership.user_id == models.User.id)
                      .join(models.Organization, models.Organization.id == models.Membership.org_id)
                      .where(models.Membership.org_id.in_(org_ids))
                      .order_by(models.User.email)).all()
    counts = fail_counts(db, list({u.email for u, _, _ in rows}))
    people_map = {}
    for u, m, o in rows:
        if q.strip() and q.strip().lower() not in (u.email + " " + u.name).lower():
            continue
        entry = people_map.setdefault(u.id, {"id": u.id, "email": u.email, "name": u.name,
                                            "account_type": u.account_type,
                                            "last_login_at": u.last_login_at, "disabled": u.disabled,
                                            "locked": locked(*counts.get(u.email, (0, 0))), "orgs": []})
        entry["orgs"].append({"org": o.name, "role": m.role})
    return {"people": list(people_map.values())[:500]}


@router.post("/{scope_name}/{target_id}/people/{user_id}/reset-email")
def person_reset(scope_name: str, target_id: str, user_id: str, request: Request,
                 user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = ctx_for(db, user, scope_name, target_id)
    person = person_in_scope(db, ctx, user_id)
    need_outranked(db, ctx, person)
    if settings.mail_backend == "none":
        raise HTTPException(400, "email is not set up on this server")
    ratelimit.hit("it-reset:" + person.id, 3, 3600, "a reset email was sent recently")
    send_reset(db, person)
    audit.log(db, "it.reset_email", user, ip=client_ip(request), target=person.id, scope=ctx["scope"], scope_id=target_id)
    db.commit()
    return {"ok": True}


@router.post("/{scope_name}/{target_id}/people/{user_id}/unlock")
def person_unlock(scope_name: str, target_id: str, user_id: str, request: Request,
                  user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = ctx_for(db, user, scope_name, target_id)
    person = person_in_scope(db, ctx, user_id)
    need_outranked(db, ctx, person)
    ratelimit.clear("login-fail:" + person.email)
    ratelimit.clear_prefix("login-try:" + person.email + "|")
    audit.log(db, "it.unlock", user, ip=client_ip(request), target=person.id, scope=ctx["scope"], scope_id=target_id)
    db.commit()
    return {"ok": True}


@router.get("/{scope_name}/{target_id}/join-requests")
def join_requests(scope_name: str, target_id: str, user: models.User = Depends(current_user),
                  db: Session = Depends(get_db)):
    ctx = ctx_for(db, user, scope_name, target_id)
    org_ids = scope_org_ids(db, ctx)
    if not org_ids:
        return {"requests": []}
    rows = db.execute(select(models.JoinRequest, models.User, models.Organization)
                      .join(models.User, models.User.id == models.JoinRequest.user_id)
                      .join(models.Organization, models.Organization.id == models.JoinRequest.org_id)
                      .where(models.JoinRequest.org_id.in_(org_ids), models.JoinRequest.status == "pending")
                      .order_by(models.JoinRequest.created_at.desc())).all()
    return {"requests": [{"id": j.id, "org_id": o.id, "org": o.name, "school": o.school, "email": u.email,
                          "name": u.name, "school_email": j.school_email, "message": j.message,
                          "created_at": j.created_at} for j, u, o in rows]}


@router.get("/{scope_name}/{target_id}/admins")
def admins(scope_name: str, target_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = ctx_for(db, user, scope_name, target_id)
    conditions = [(models.AdminRole.scope == "school") & models.AdminRole.target_id.in_(list(ctx["school_ids"]) or [""])]
    if ctx["scope"] == "district":
        conditions.append((models.AdminRole.scope == "district") & (models.AdminRole.target_id == ctx["district"].id))
    stmt = select(models.AdminRole).where(or_(*conditions))
    return {"admins": role_rows(db, db.scalars(stmt.order_by(models.AdminRole.created_at)).all()),
            "schools": [{"id": s.id, "name": s.name, "staff_domains": s.staff_domains or []} for s in ctx["schools"]]}


@router.post("/{scope_name}/{target_id}/admins")
def add_admin(scope_name: str, target_id: str, body: GrantIn, request: Request,
              user: models.User = Depends(sudo_user), db: Session = Depends(get_db)):
    ctx = ctx_for(db, user, scope_name, target_id)
    school_id = body.school_id or (ctx["school"].id if ctx["school"] else "")
    if school_id not in ctx["school_ids"]:
        raise HTTPException(400, "choose a college in this area")
    role = grant_role(db, request, user, "school", db.get(models.School, school_id), body.email)
    return {"ok": True, "id": role.id}


@router.delete("/{scope_name}/{target_id}/admins/{role_id}")
def remove_admin(scope_name: str, target_id: str, role_id: str, request: Request,
                 user: models.User = Depends(sudo_user), db: Session = Depends(get_db)):
    ctx = ctx_for(db, user, scope_name, target_id)
    role = db.get(models.AdminRole, role_id)
    in_area = role is not None and ((role.scope == "school" and role.target_id in ctx["school_ids"])
                                    or (role.scope == "district" and role.target_id == ctx["district"].id))
    if not in_area:
        raise HTTPException(404, "role not found")
    revoke_role(db, request, user, role)
    return {"ok": True}


def district_ctx(db, user, scope_name, target_id):
    ctx = ctx_for(db, user, scope_name, target_id)
    if ctx["scope"] != "district":
        raise HTTPException(404, "not found")
    return ctx


@router.get("/{scope_name}/{target_id}/schools")
def schools(scope_name: str, target_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = district_ctx(db, user, scope_name, target_id)
    return {"district": {"id": ctx["district"].id, "name": ctx["district"].name,
                         "staff_domains": ctx["district"].staff_domains or []},
            "schools": [dict(school_payload(s), staff_domains=s.staff_domains or []) for s in ctx["schools"]]}


@router.post("/{scope_name}/{target_id}/schools")
def add_school(scope_name: str, target_id: str, body: SchoolIn, request: Request,
               user: models.User = Depends(sudo_user), db: Session = Depends(get_db)):
    ctx = district_ctx(db, user, scope_name, target_id)
    school = find_or_create_school(db, ctx["district"], clean_name(body.name, "school name"), clean_domains(body.domains))
    if body.staff_domains:
        school.staff_domains = clean_staff(body.staff_domains)
    audit.log(db, "school.added", user, ip=client_ip(request), school=school.name, district=ctx["district"].id)
    db.commit()
    return school_payload(school)


@router.patch("/{scope_name}/{target_id}/schools/{school_id}")
def edit_school(scope_name: str, target_id: str, school_id: str, body: SchoolPatch, request: Request,
                user: models.User = Depends(sudo_user), db: Session = Depends(get_db)):
    ctx = district_ctx(db, user, scope_name, target_id)
    if school_id not in ctx["school_ids"]:
        raise HTTPException(404, "school not found")
    school = db.get(models.School, school_id)
    if body.name is not None:
        school.name = clean_name(body.name, "school name")
    if body.domains is not None:
        school.email_domains = clean_domains(body.domains)
    if body.staff_domains is not None:
        school.staff_domains = clean_staff(body.staff_domains)
    if body.active is not None:
        school.active = body.active
    audit.log(db, "school.edited", user, ip=client_ip(request), school=school.name, domains=school.email_domains,
              staff_domains=school.staff_domains)
    db.commit()
    return dict(school_payload(school), staff_domains=school.staff_domains or [])


def scope_requests_stmt(ctx):
    stmt = select(models.SchoolRequest, models.User).join(models.User, models.User.id == models.SchoolRequest.user_id)
    if ctx["scope"] == "district":
        return stmt.where(or_((models.SchoolRequest.kind == "school") & (models.SchoolRequest.district_id == ctx["district"].id),
                              (models.SchoolRequest.kind == "org") & models.SchoolRequest.school_id.in_(list(ctx["school_ids"]) or [""])))
    return stmt.where(models.SchoolRequest.kind == "org", models.SchoolRequest.school_id == ctx["school"].id)


@router.get("/{scope_name}/{target_id}/requests")
def requests_in_scope(scope_name: str, target_id: str, user: models.User = Depends(current_user),
                      db: Session = Depends(get_db)):
    ctx = ctx_for(db, user, scope_name, target_id)
    rows = db.execute(scope_requests_stmt(ctx).order_by(models.SchoolRequest.status != "pending",
                                                         models.SchoolRequest.created_at.desc()).limit(200)).all()
    return {"requests": request_rows(db, rows)}


def scoped_request(db, ctx, request_id):
    row = db.execute(scope_requests_stmt(ctx).where(models.SchoolRequest.id == request_id)).first()
    if row is None or row[0].status != "pending":
        raise HTTPException(404, "request not found")
    return row[0]


@router.post("/{scope_name}/{target_id}/requests/{request_id}/approve")
def approve_in_scope(scope_name: str, target_id: str, request_id: str, body: ApproveIn, request: Request,
                     user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = ctx_for(db, user, scope_name, target_id)
    return approve_school_request(db, request, user, scoped_request(db, ctx, request_id), body)


@router.post("/{scope_name}/{target_id}/requests/{request_id}/reject")
def reject_in_scope(scope_name: str, target_id: str, request_id: str, body: DecideIn, request: Request,
                    user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = ctx_for(db, user, scope_name, target_id)
    return reject_school_request(db, request, user, scoped_request(db, ctx, request_id), body)


@router.get("/{scope_name}/{target_id}/activity")
def activity(scope_name: str, target_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = ctx_for(db, user, scope_name, target_id)
    org_ids = scope_org_ids(db, ctx)
    since = time.time() - 90 * 86400
    if not org_ids:
        return {"events": []}
    rows = db.execute(select(models.AuditEvent, models.User.email, models.Organization.name)
                      .outerjoin(models.User, models.User.id == models.AuditEvent.user_id)
                      .outerjoin(models.Organization, models.Organization.id == models.AuditEvent.org_id)
                      .where(models.AuditEvent.org_id.in_(org_ids), models.AuditEvent.created_at > since)
                      .order_by(models.AuditEvent.id.desc()).limit(300)).all()
    return {"events": [{"at": e.created_at, "action": e.action, "user": email or "", "org": org or "", "ip": e.ip,
                        "detail": e.detail} for e, email, org in rows]}
