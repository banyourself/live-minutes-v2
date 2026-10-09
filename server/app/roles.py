from fastapi import HTTPException
from sqlalchemy import select

from . import audit, mailer, models, scope
from .deps import client_ip
from .settings import settings

LABEL = {"district": "district IT", "school": "college IT"}


def role_rows(db, roles):
    out = []
    for r in roles:
        u = db.get(models.User, r.user_id)
        target = db.get(models.District if r.scope == "district" else models.School, r.target_id)
        out.append({"id": r.id, "scope": r.scope, "target_id": r.target_id, "target": target.name if target else "",
                    "email": u.email if u else "", "name": u.name if u else "", "staff_email": r.staff_email,
                    "created_at": r.created_at})
    return out


def grant_role(db, request, granter, scope_name, target, email):
    if not scope.can_grant(db, granter, scope_name, target):
        raise HTTPException(403, "you cannot grant %s here" % LABEL[scope_name])
    who = db.scalar(select(models.User).where(models.User.email == (email or "").strip().lower()))
    if who is None or who.email_verified_at is None or who.disabled:
        raise HTTPException(400, "there is no active, confirmed account with that email")
    if who.id == granter.id:
        raise HTTPException(400, "you cannot give yourself a role")
    if who.account_type not in models.IT_TYPES:
        raise HTTPException(400, "only Staff or IT accounts can hold IT roles; %s is set up as %s" % (
            who.email, who.account_type or "no account type"))
    proof = scope.staff_proof(db, who, scope_name, target)
    if proof is None:
        domains = sorted(scope.staff_domains_for(db, scope_name, target))
        if not domains:
            raise HTTPException(400, "add staff email domains for %s first" % target.name)
        raise HTTPException(400, "%s needs a confirmed staff email ending in %s before they can be %s" % (
            who.email, " or ".join("@" + d for d in domains), LABEL[scope_name]))
    existing = db.scalar(select(models.AdminRole).where(models.AdminRole.user_id == who.id,
                                                        models.AdminRole.scope == scope_name,
                                                        models.AdminRole.target_id == target.id))
    if existing is not None:
        return existing
    role = models.AdminRole(user_id=who.id, scope=scope_name, target_id=target.id, staff_email=proof.email,
                            granted_by=granter.id)
    db.add(role)
    mailer.queue(db, who.email, "You are now %s for %s on Live Minutes" % (LABEL[scope_name], target.name[:120]),
                 "%s made you %s for %s. Open the IT console at %s/manage" % (
                     granter.name or granter.email, LABEL[scope_name], target.name, settings.public_url))
    audit.log(db, "role.granted", granter, ip=client_ip(request), target=who.id, email=who.email, scope=scope_name,
              scope_id=target.id, staff_email=proof.email)
    db.commit()
    return role


def revoke_role(db, request, actor, role):
    target = db.get(models.District if role.scope == "district" else models.School, role.target_id)
    allowed = actor.is_platform_admin or (role.scope == "school" and target is not None
                                          and scope.can_grant(db, actor, "school", target))
    if not allowed or (role.user_id == actor.id and not actor.is_platform_admin):
        raise HTTPException(403, "you cannot remove this role")
    audit.log(db, "role.revoked", actor, ip=client_ip(request), target=role.user_id, scope=role.scope,
              scope_id=role.target_id)
    db.delete(role)
    db.commit()
