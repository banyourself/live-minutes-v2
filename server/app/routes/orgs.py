import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit, governance, mailer, models, names, officers, personal, ratelimit, runtime, scope
from ..db import get_db
from ..deps import client_ip, current_user, membership, platform_admin, require_role, sudo_user
from ..security import new_token, token_hash
from ..settings import settings
from .directory import (TYPE_WORD, active_school, clean_name, need_type, open_request, org_name_taken,
                        verified_for_school)

router = APIRouter(prefix="/api/orgs", tags=["organizations"])


class OrgIn(BaseModel):
    name: str
    school_id: str = ""
    allow_duplicate: bool = False


class OrgPatch(BaseModel):
    name: str | None = None
    school: str | None = None
    style_rules: str | None = None
    aliases: list[dict] | None = None
    shared_accounts: list[dict] | None = None
    public_archive: bool | None = None
    default_template_id: str | None = None
    example_template_id: str | None = None


class InviteIn(BaseModel):
    email: str
    role: str = "member"


class RoleIn(BaseModel):
    role: str


def org_payload(org, district, role):
    cfg = org.settings or {}
    return {"id": org.id, "name": org.name, "school": org.school, "district": district.name,
            "district_id": district.id, "school_id": org.school_id, "role": role,
            "style_rules": cfg.get("style_rules", ""),
            "aliases": cfg.get("aliases", []), "shared_accounts": cfg.get("shared_accounts", []),
            "public_archive": bool(cfg.get("public_archive")),
            "allowed_domains": district.allowed_domains or [],
            "default_template_id": cfg.get("default_template_id", ""), "example_template_id": cfg.get("example_template_id", "")}


@router.post("")
def create_org(body: OrgIn, request: Request, user: models.User = Depends(current_user),
               db: Session = Depends(get_db)):
    if not body.school_id:
        raise HTTPException(400, "choose your college from the list; new colleges and districts are requested "
                                 "from the organization page")
    school = active_school(db, body.school_id)
    name = clean_name(body.name, "organization name")
    if org_name_taken(db, school.id, name):
        raise HTTPException(409, "%s already has an organization named %s; request to join it instead"
                            % (school.name, name))
    district = db.get(models.District, school.district_id)
    it_staff = user.is_platform_admin or school.id in scope.school_ids(db, user)
    if not it_staff:
        kind = need_type(user)
        proof = verified_for_school(db, user, school)
        if proof is None:
            raise HTTPException(403, "confirm your %s %s email first" % (school.name, TYPE_WORD[kind]))
        advisor_ok = (user.account_type in ("faculty", "staff")
                      and governance.org_rules_for(db, school.id, district.id)["advisors_create_orgs"])
        if not advisor_ok:
            ratelimit.hit("org-request:" + user.id, 5, 86400)
            sr = open_request(db, request, user, "org", district, school, district.name, school.name, name, proof)
            return {"status": "pending", "id": sr.id}
    found = names.similar(db.scalars(select(models.Organization).where(models.Organization.school_id == school.id)).all(),
                          name)
    if found and not body.allow_duplicate:
        raise HTTPException(409, "this looks like %s, which already exists at %s; confirm it is a different "
                                 "organization" % (" or ".join(f["name"] for f in found), school.name))
    org = models.Organization(district_id=school.district_id, school_id=school.id, school=school.name, name=name,
                              settings={})
    db.add(org)
    db.flush()
    db.add(models.Membership(user_id=user.id, org_id=org.id, role="owner"))
    audit.log(db, "org.created", user, org.id, client_ip(request), name=org.name, school=school.name)
    db.commit()
    return dict(org_payload(org, district, "owner"), status="created")


def can_delete(db, user, org):
    if user.is_platform_admin or scope.covers_org(db, user, org):
        return True
    if personal.is_personal(db, org.id):
        return db.scalar(select(models.Membership.id).where(models.Membership.org_id == org.id,
                                                            models.Membership.user_id == user.id,
                                                            models.Membership.role == "owner")) is not None
    if not governance.org_rules_for(db, org.school_id, org.district_id)["allow_org_delete"]:
        return False
    return officers.authority(db, user, org).has("delete_organization")


@router.get("/{org_id}")
def get_org(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    org, role = require_role(db, user, org_id)
    return dict(org_payload(org, db.get(models.District, org.district_id), role), can_delete=can_delete(db, user, org))


@router.delete("/{org_id}")
def delete_org(org_id: str, request: Request, confirm: str = "", user: models.User = Depends(sudo_user),
               db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "member")
    if not can_delete(db, user, org):
        raise HTTPException(403, "only college or district IT can delete organizations here")
    if confirm.strip().lower() != org.name.strip().lower():
        raise HTTPException(400, "type the organization's name to confirm")
    governance.check_hold(db, org, "delete this organization")
    audit.log(db, "org.deleted", user, org.id, client_ip(request), name=org.name)
    governance.delete_org(db, org)
    db.commit()
    return {"ok": True}


@router.patch("/{org_id}")
def patch_org(org_id: str, body: OrgPatch, request: Request, user: models.User = Depends(current_user),
              db: Session = Depends(get_db)):
    org, role = require_role(db, user, org_id, "owner")
    if body.name is not None:
        org.name = body.name.strip()[:200] or org.name
    if body.school is not None:
        org.school = body.school.strip()[:200]
    cfg = dict(org.settings or {})
    if body.style_rules is not None:
        cfg["style_rules"] = body.style_rules[:6000]
    if body.aliases is not None:
        cfg["aliases"] = [{"from": str(a.get("from", ""))[:120], "to": str(a.get("to", ""))[:120]}
                          for a in body.aliases[:200] if a.get("from")]
    if body.public_archive is not None and bool(cfg.get("public_archive")) != body.public_archive:
        cfg["public_archive"] = body.public_archive
        audit.log(db, "org.public_archive", user, org_id, client_ip(request), on=body.public_archive)
    if body.shared_accounts is not None:
        cfg["shared_accounts"] = [
            {"name": " ".join(str(s.get("name", "")).split())[:120],
             "people": [" ".join(str(p).split())[:80] for p in (s.get("people") if isinstance(s.get("people"), list) else [])[:20]
                        if str(p).strip()]}
            for s in body.shared_accounts[:50] if str(s.get("name", "")).strip()]
    for field, purpose in (("default_template_id", "template"), ("example_template_id", "example")):
        value = getattr(body, field)
        if value is None:
            continue
        if value:
            t = db.get(models.Template, value)
            if t is None or t.org_id != org.id or t.purpose != purpose:
                raise HTTPException(400, "choose one of this organization's %ss" % ("templates" if purpose == "template" else "examples"))
        cfg[field] = value
    org.settings = cfg
    audit.log(db, "org.updated", user, org.id, client_ip(request))
    db.commit()
    return org_payload(org, db.get(models.District, org.district_id), role)


@router.put("/{org_id}/domains")
def set_domains(org_id: str, body: dict, request: Request, user: models.User = Depends(platform_admin),
                db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "owner")
    district = db.get(models.District, org.district_id)
    domains = sorted({str(d).strip().lower().lstrip("@") for d in body.get("domains", []) if "." in str(d)})
    district.allowed_domains = domains[:20]
    audit.log(db, "district.domains", user, org.id, client_ip(request), domains=domains)
    db.commit()
    return {"allowed_domains": district.allowed_domains}


@router.get("/{org_id}/members")
def members(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, org_id, "member")
    rows = db.execute(select(models.Membership, models.User).join(models.User, models.User.id == models.Membership.user_id)
                      .where(models.Membership.org_id == org_id).order_by(models.User.email)).all()
    invites = db.scalars(select(models.Invite).where(models.Invite.org_id == org_id,
                                                     models.Invite.accepted_at.is_(None))).all()
    titles = {}
    for t, p in db.execute(officers.active_query(org_id)).all():
        titles.setdefault(t.user_id, []).append(p.name)
    return {"members": [{"id": m.id, "user_id": u.id, "email": u.email, "name": u.name, "role": m.role,
                         "account_type": u.account_type, "positions": titles.get(u.id, []),
                         "effective_role": officers.effective_role(db, m)}
                        for m, u in rows],
            "invites": [{"id": i.id, "email": i.email, "role": i.role, "created_at": i.created_at,
                         "expires_at": i.expires_at, "expired": bool(i.expires_at and i.expires_at < time.time())}
                        for i in invites]}


@router.post("/{org_id}/invites")
def invite(org_id: str, body: InviteIn, request: Request, user: models.User = Depends(current_user),
           db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "owner")
    if personal.is_personal(db, org_id) and not user.is_platform_admin:
        raise HTTPException(403, "a personal workspace is private to you; share minutes by downloading the Word file")
    if body.role not in models.ROLES:
        raise HTTPException(400, "unknown role")
    if body.role == "owner" and not may_grant_owner(db, user, org):
        raise HTTPException(403, "only organization owners and IT can invite someone with permanent full access")
    email = body.email.strip().lower()
    if "@" not in email or len(email) > 320:
        raise HTTPException(400, "enter a valid email address")
    ratelimit.hit("invite:" + org_id, 100, 86400, "this organization has sent many invites today; try again tomorrow")
    org = db.get(models.Organization, org_id)
    token = new_token()
    link = settings.public_url + "/invite/" + token
    db.add(models.Invite(org_id=org_id, email=email, role=body.role, token_hash=token_hash(token),
                         created_by=user.id, expires_at=time.time() + int(runtime.get("invite_days")) * 86400))
    mailer.queue(db, email, "You're invited to %s on Live Minutes" % org.name[:120],
                 "%s invited you to join %s as %s.\n\nOpen this link to accept:\n\n%s\n\n"
                 "The link works for %d days." % (user.name or user.email, org.name, body.role, link,
                                                  int(runtime.get("invite_days"))))
    audit.log(db, "invite.created", user, org_id, client_ip(request), email=email, role=body.role)
    db.commit()
    emailed = settings.mail_backend != "none"
    return {"link": "" if emailed else link, "email": email, "role": body.role, "emailed": emailed}


@router.delete("/{org_id}/invites/{invite_id}")
def revoke_invite(org_id: str, invite_id: str, request: Request, user: models.User = Depends(current_user),
                  db: Session = Depends(get_db)):
    require_role(db, user, org_id, "owner")
    inv = db.get(models.Invite, invite_id)
    if inv is None or inv.org_id != org_id:
        raise HTTPException(404, "invite not found")
    audit.log(db, "invite.revoked", user, org_id, client_ip(request), email=inv.email)
    db.delete(inv)
    db.commit()
    return {"ok": True}


def owner_count(db, org_id):
    return db.scalar(select(func.count()).select_from(models.Membership)
                     .where(models.Membership.org_id == org_id, models.Membership.role == "owner"))


def top_rank(db, org_id, user_id):
    m = db.scalar(select(models.Membership).where(models.Membership.org_id == org_id, models.Membership.user_id == user_id))
    ranks = [p.rank for _, p in officers.held(db, org_id, user_id)]
    if m is not None and m.role == "owner":
        ranks.append(100)
    return max(ranks, default=0)


def may_grant_owner(db, user, org):
    if user.is_platform_admin or scope.covers_org(db, user, org):
        return True
    me = membership(db, user, org.id)
    return me is not None and me.role == "owner"


def guard_member(db, user, org, m, role=None):
    if user.is_platform_admin or scope.covers_org(db, user, org):
        return
    if m.user_id == user.id:
        if role is not None:
            raise HTTPException(403, "ask another owner or IT to change your own access")
        return
    me = membership(db, user, org.id)
    real_owner = me is not None and me.role == "owner"
    if (role == "owner" or m.role == "owner") and not real_owner:
        raise HTTPException(403, "only organization owners and IT can give or take away permanent full access")
    held = max((p.rank for _, p in officers.held(db, org.id, m.user_id)), default=0)
    if real_owner:
        if held >= 100:
            raise HTTPException(403, "ask IT to change or remove the advisor")
    elif top_rank(db, org.id, m.user_id) >= top_rank(db, org.id, user.id):
        raise HTTPException(403, "you can't change or remove someone whose position ranks at or above yours; ask IT")


@router.patch("/{org_id}/members/{membership_id}")
def set_role(org_id: str, membership_id: str, body: RoleIn, request: Request,
             user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "owner")
    m = db.get(models.Membership, membership_id)
    if m is None or m.org_id != org_id:
        raise HTTPException(404, "member not found")
    if body.role not in models.ROLES:
        raise HTTPException(400, "unknown role")
    guard_member(db, user, org, m, body.role)
    if m.role == "owner" and body.role != "owner" and owner_count(db, org_id) <= 1:
        raise HTTPException(400, "an organization needs at least one owner")
    m.role = body.role
    audit.log(db, "member.role", user, org_id, client_ip(request), member=m.user_id, role=body.role)
    db.commit()
    return {"ok": True}


@router.delete("/{org_id}/members/{membership_id}")
def remove_member(org_id: str, membership_id: str, request: Request, user: models.User = Depends(current_user),
                  db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "owner")
    m = db.get(models.Membership, membership_id)
    if m is None or m.org_id != org_id:
        raise HTTPException(404, "member not found")
    guard_member(db, user, org, m)
    if m.role == "owner" and owner_count(db, org_id) <= 1:
        raise HTTPException(400, "an organization needs at least one owner")
    officers.end_all_for(db, org_id, m.user_id, user.id, "left organization")
    db.delete(m)
    audit.log(db, "member.removed", user, org_id, client_ip(request), member=m.user_id)
    db.commit()
    return {"ok": True}


@router.get("/{org_id}/audit")
def audit_log(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, org_id, "owner")
    rows = db.execute(select(models.AuditEvent, models.User.email)
                      .outerjoin(models.User, models.User.id == models.AuditEvent.user_id)
                      .where(models.AuditEvent.org_id == org_id)
                      .order_by(models.AuditEvent.id.desc()).limit(300)).all()
    return {"events": [{"at": e.created_at, "action": e.action, "user": email or "", "detail": e.detail}
                       for e, email in rows]}
