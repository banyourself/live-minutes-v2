import csv
import io
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, mailer, models, ratelimit, runtime, school_sso, scope, sso, validation
from ..db import get_db
from ..deps import client_ip, current_user, require_role, sudo_user
from . import orgs as org_routes
from ..security import new_token, token_hash
from ..settings import settings

router = APIRouter(tags=["provisioning"])
MAX_ROWS = 200
DAILY = 300


class SsoIn(BaseModel):
    microsoft_tenants: list[str] = []
    google_domains: list[str] = []
    auto_setup: bool = True


class BulkIn(BaseModel):
    csv: str
    role: str = "member"
    send: bool = True


def district_scope(db, user, scope_name, target_id):
    ctx = scope.resolve(db, user, scope_name, target_id)
    if ctx["scope"] != "district":
        raise HTTPException(403, "school sign-in is set for the whole district by district IT")
    return ctx


def sso_payload(district):
    return dict(school_sso.config(district), redirect_uri=sso.redirect_uri("microsoft"),
                google_redirect_uri=sso.redirect_uri("google"),
                microsoft_app=bool(settings.microsoft_client_id and settings.microsoft_client_secret),
                google_app=bool(settings.google_client_id and settings.google_client_secret),
                client_id=settings.microsoft_client_id or "")


@router.get("/api/manage/{scope_name}/{target_id}/sso")
def get_sso(scope_name: str, target_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = district_scope(db, user, scope_name, target_id)
    return sso_payload(ctx["district"])


@router.put("/api/manage/{scope_name}/{target_id}/sso")
def put_sso(scope_name: str, target_id: str, body: SsoIn, request: Request, user: models.User = Depends(sudo_user),
            db: Session = Depends(get_db)):
    ctx = district_scope(db, user, scope_name, target_id)
    cfg = school_sso.clean(body.microsoft_tenants, body.google_domains, body.auto_setup)
    clash = school_sso.taken(db, ctx["district"].id, cfg)
    if clash:
        raise HTTPException(409, "%s is already set up for %s; ask the platform owner if it belongs to you" % (
            clash[1], clash[0]))
    d = ctx["district"]
    d.settings = dict(d.settings or {}, sso=cfg)
    audit.log(db, "district.sso", user, ip=client_ip(request), district=d.id, tenants=",".join(cfg["microsoft_tenants"]),
              domains=",".join(cfg["google_domains"]), auto_setup=cfg["auto_setup"])
    db.commit()
    return sso_payload(d)


def parse_rows(text):
    rows = list(csv.reader(io.StringIO(text.strip())))
    if rows and rows[0] and "email" in [c.strip().lower() for c in rows[0]]:
        head = [c.strip().lower() for c in rows[0]]
        idx = {k: head.index(k) for k in ("email", "role", "name") if k in head}
        rows = rows[1:]
    else:
        idx = {"email": 0, "role": 1, "name": 2}
    out = []
    for r in rows:
        get = (lambda k: r[idx[k]].strip() if k in idx and idx[k] < len(r) else "")
        if any(c.strip() for c in r):
            out.append({"email": get("email"), "role": get("role").lower(), "name": get("name")})
    return out


@router.post("/api/orgs/{org_id}/invites/bulk")
def bulk_invite(org_id: str, body: BulkIn, request: Request, user: models.User = Depends(current_user),
                db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "owner")
    if body.role == "owner" and not org_routes.may_grant_owner(db, user, org):
        raise HTTPException(403, "only organization owners and IT can invite someone with permanent full access")
    if len(body.csv) > 200_000:
        raise HTTPException(413, "the list is too large")
    if body.role not in models.ROLES:
        raise HTTPException(400, "unknown role")
    rows = parse_rows(body.csv)
    if not rows:
        raise HTTPException(400, "paste at least one email address")
    if len(rows) > MAX_ROWS:
        raise HTTPException(400, "invite up to %d people at a time" % MAX_ROWS)
    used = ratelimit.count("invite:" + org_id, 86400)
    if used + len(rows) > DAILY:
        raise HTTPException(429, "this organization can send %d more invites today" % max(0, DAILY - used))
    members = set(db.scalars(select(models.User.email).join(models.Membership, models.Membership.user_id == models.User.id)
                             .where(models.Membership.org_id == org_id)).all())
    pending = set(db.scalars(select(models.Invite.email).where(models.Invite.org_id == org_id,
                                                               models.Invite.accepted_at.is_(None),
                                                               models.Invite.expires_at > time.time())).all())
    days = int(runtime.get("invite_days"))
    result = {"invited": [], "skipped": []}
    seen = set()
    for i, row in enumerate(rows, 1):
        try:
            email = validation.clean_email(row["email"], check_dns=False)
        except HTTPException as exc:
            result["skipped"].append({"row": i, "email": row["email"][:120], "reason": exc.detail})
            continue
        role = row["role"] or body.role
        if role not in models.ROLES:
            result["skipped"].append({"row": i, "email": email, "reason": "unknown role " + role[:20]})
            continue
        if role == "owner" and body.role != "owner":
            role = body.role
        reason = ("listed twice" if email in seen else "already a member" if email in members
                  else "already invited" if email in pending else "")
        seen.add(email)
        if reason:
            result["skipped"].append({"row": i, "email": email, "reason": reason})
            continue
        token = new_token()
        link = settings.public_url + "/invite/" + token
        db.add(models.Invite(org_id=org_id, email=email, role=role, token_hash=token_hash(token), created_by=user.id,
                             expires_at=time.time() + days * 86400))
        if body.send:
            mailer.queue(db, email, "You're invited to %s on Live Minutes" % org.name[:120],
                         "%s invited you to join %s as %s.\n\nOpen this link to accept:\n\n%s\n\nThe link works for %d days."
                         % (user.name or user.email, org.name, role, link, days))
        result["invited"].append({"row": i, "email": email, "role": role, "link": "" if body.send else link})
    audit.log(db, "invite.bulk", user, org_id, client_ip(request), invited=len(result["invited"]),
              skipped=len(result["skipped"]))
    db.commit()
    for _ in result["invited"]:
        ratelimit.record("invite:" + org_id)
    return result
