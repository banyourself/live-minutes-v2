import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from .. import audit, captcha, governance, mailer, models, personal, ratelimit, runtime, sso, twofactor
from ..db import get_db
from ..deps import client_ip, platform_admin, sudo_admin
from ..roles import grant_role, revoke_role, role_rows
from ..security import new_token, token_hash
from ..settings import settings
from .auth import LINK_MINUTES, issue_token, mark_verified, revoke_credentials, revoke_sessions, security_mail, send_reset
from .auth import sudo as confirm_sudo

router = APIRouter(prefix="/api/admin", tags=["admin"])


class SudoIn(BaseModel):
    password: str


class FlagIn(BaseModel):
    on: bool


class MemberIn(BaseModel):
    email: str
    role: str = "member"


class PersonalInviteIn(BaseModel):
    email: str
    name: str = ""


class SettingsIn(BaseModel):
    values: dict


def page(offset, limit):
    return max(0, int(offset)), min(max(1, int(limit)), 200)


def fail_counts(db, emails):
    keys = ["login-fail:" + e for e in emails]
    if not keys:
        return {}
    now = time.time()
    rows = db.execute(select(models.RateEvent.key,
                             func.count().filter(models.RateEvent.created_at > now - 900),
                             func.count())
                      .where(models.RateEvent.key.in_(keys), models.RateEvent.created_at > now - 86400)
                      .group_by(models.RateEvent.key)).all()
    return {k.split(":", 1)[1]: (short or 0, day or 0) for k, short, day in rows}


def locked(short, day):
    return short >= int(runtime.get("lock_short")) or day >= int(runtime.get("lock_day"))


@router.post("/sudo")
def sudo(body: SudoIn, request: Request, user: models.User = Depends(platform_admin), db: Session = Depends(get_db)):
    return confirm_sudo(body, request, user, db)


@router.get("/overview")
def overview(user: models.User = Depends(platform_admin), db: Session = Depends(get_db)):
    now = time.time()
    def count(stmt):
        return db.scalar(stmt) or 0
    users = select(func.count()).select_from(models.User)
    meetings = dict(db.execute(select(models.Meeting.status, func.count()).group_by(models.Meeting.status)).all())
    jobs = dict(db.execute(select(models.Job.status, func.count()).group_by(models.Job.status)).all())
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    beat = runtime.last_heartbeat()
    return {
        "users": {"total": count(users), "verified": count(users.where(models.User.email_verified_at.is_not(None))),
                  "admins": count(users.where(models.User.is_platform_admin.is_(True))),
                  "disabled": count(users.where(models.User.disabled.is_(True))),
                  "new_7d": count(users.where(models.User.created_at > now - 7 * 86400)),
                  "active_24h": count(users.where(models.User.last_login_at > now - 86400)),
                  "by_type": dict(db.execute(select(models.User.account_type, func.count())
                                             .group_by(models.User.account_type)).all())},
        "orgs": count(select(func.count()).select_from(models.Organization)),
        "districts": count(select(func.count()).select_from(models.District)),
        "schools": count(select(func.count()).select_from(models.School)),
        "meetings": {"total": sum(meetings.values()), **meetings},
        "jobs": jobs,
        "requests": {"join": count(select(func.count()).select_from(models.JoinRequest)
                                   .where(models.JoinRequest.status == "pending")),
                     "school": count(select(func.count()).select_from(models.SchoolRequest)
                                     .where(models.SchoolRequest.status == "pending"))},
        "email": {"sent_24h": count(select(func.count()).select_from(models.OutboxEmail)
                                    .where(models.OutboxEmail.sent_at > now - 86400)),
                  "pending": count(select(func.count()).select_from(models.OutboxEmail)
                                   .where(models.OutboxEmail.sent_at.is_(None), models.OutboxEmail.attempts < mailer.MAX_ATTEMPTS)),
                  "failed": count(select(func.count()).select_from(models.OutboxEmail)
                                  .where(models.OutboxEmail.sent_at.is_(None), models.OutboxEmail.attempts >= mailer.MAX_ATTEMPTS))},
        "security": {"failed_logins_24h": count(select(func.count()).select_from(models.RateEvent)
                                                .where(models.RateEvent.key.like("login-fail:%"),
                                                       models.RateEvent.created_at > now - 86400))},
        "health": {"database": db_ok, "worker_seen_seconds_ago": round(now - beat) if beat else None,
                   "worker_ok": bool(beat) and now - beat < 180, "mail": settings.mail_backend,
                   "turnstile": captcha.required(), "sso": [p["id"] for p in sso.configured()],
                   "maintenance": bool(runtime.get("maintenance_mode")), "public_url": settings.public_url},
    }


def user_row(db, u, counts=None):
    short, day = (counts if counts is not None else fail_counts(db, [u.email])).get(u.email, (0, 0))
    return {"id": u.id, "email": u.email, "name": u.name, "account_type": u.account_type,
            "verified": u.email_verified_at is not None,
            "verified_via": u.verified_via, "admin": u.is_platform_admin, "disabled": u.disabled,
            "has_password": bool(u.password_hash), "two_factor": bool(u.totp_enabled_at),
            "created_at": u.created_at, "last_login_at": u.last_login_at,
            "orgs": db.scalar(select(func.count()).select_from(models.Membership)
                              .where(models.Membership.user_id == u.id)) or 0,
            "failed_15m": short, "failed_24h": day, "locked": locked(short, day)}


@router.get("/users")
def list_users(q: str = "", type: str = "", offset: int = 0, limit: int = 50,
               user: models.User = Depends(platform_admin), db: Session = Depends(get_db)):
    offset, limit = page(offset, limit)
    stmt = select(models.User)
    if type == "none":
        stmt = stmt.where(models.User.account_type == "")
    elif type in models.ACCOUNT_TYPES:
        stmt = stmt.where(models.User.account_type == type)
    if q.strip():
        like = "%" + q.strip().lower() + "%"
        stmt = stmt.where(or_(func.lower(models.User.email).like(like), func.lower(models.User.name).like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(models.User.created_at.desc()).offset(offset).limit(limit)).all()
    counts = fail_counts(db, [u.email for u in rows])
    return {"total": total, "users": [user_row(db, u, counts) for u in rows]}


def target_user(db, user_id):
    u = db.get(models.User, user_id)
    if u is None:
        raise HTTPException(404, "user not found")
    return u


@router.get("/users/{user_id}")
def user_detail(user_id: str, user: models.User = Depends(platform_admin), db: Session = Depends(get_db)):
    u = target_user(db, user_id)
    memberships = db.execute(select(models.Membership, models.Organization)
                             .join(models.Organization, models.Organization.id == models.Membership.org_id)
                             .where(models.Membership.user_id == u.id)).all()
    sessions = db.scalars(select(models.UserSession).where(models.UserSession.user_id == u.id)
                          .order_by(models.UserSession.created_at.desc())).all()
    events = db.scalars(select(models.AuditEvent).where(models.AuditEvent.user_id == u.id)
                        .order_by(models.AuditEvent.id.desc()).limit(50)).all()
    return dict(user_row(db, u),
                memberships=[{"membership_id": m.id, "org_id": o.id, "org": o.name, "school": o.school, "role": m.role}
                             for m, o in memberships],
                school_emails=[{"email": s.email, "verified": s.verified_at is not None}
                               for s in db.scalars(select(models.SchoolEmail).where(models.SchoolEmail.user_id == u.id))],
                identities=[{"provider": i.provider, "email": i.email, "last_used_at": i.last_used_at}
                            for i in db.scalars(select(models.Identity).where(models.Identity.user_id == u.id))],
                sessions=[{"created_at": s.created_at, "last_seen_at": s.last_seen_at, "expires_at": s.expires_at,
                           "user_agent": s.user_agent} for s in sessions],
                events=[{"at": e.created_at, "action": e.action, "ip": e.ip, "detail": e.detail} for e in events],
                admin_roles=role_rows(db, db.scalars(select(models.AdminRole).where(models.AdminRole.user_id == u.id)).all()))


def act(db, request, admin, action, target, **detail):
    audit.log(db, action, admin, ip=client_ip(request), target=target.id, email=target.email, **detail)
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/reset-email")
def user_reset_email(user_id: str, request: Request, user: models.User = Depends(platform_admin),
                     db: Session = Depends(get_db)):
    u = target_user(db, user_id)
    if settings.mail_backend == "none":
        raise HTTPException(400, "email is not set up on this server; use a one-time link instead")
    send_reset(db, u)
    return act(db, request, user, "admin.reset_email", u)


@router.post("/users/{user_id}/reset-link")
def user_reset_link(user_id: str, request: Request, user: models.User = Depends(sudo_admin),
                    db: Session = Depends(get_db)):
    u = target_user(db, user_id)
    raw = issue_token(db, u, "reset")
    act(db, request, user, "admin.reset_link", u)
    return {"link": "%s/reset/%s" % (settings.public_url, raw), "minutes": LINK_MINUTES}


@router.post("/users/{user_id}/two-factor/reset")
def user_two_factor_reset(user_id: str, request: Request, user: models.User = Depends(sudo_admin),
                          db: Session = Depends(get_db)):
    target = target_user(db, user_id)
    if not target.totp_enabled_at:
        raise HTTPException(400, "two-step sign-in is not on for this account")
    twofactor.clear(target)
    revoke_sessions(db, target)
    act(db, request, user, "admin.two_factor_reset", target)
    security_mail(db, target, "Two-step sign-in was turned off for Live Minutes",
                  "A Live Minutes administrator turned off two-step sign-in for your account, usually because you lost "
                  "your phone. Every device was signed out. Turn it back on under My account.")
    db.commit()
    return user_row(db, target)


@router.post("/users/{user_id}/unlock")
def user_unlock(user_id: str, request: Request, user: models.User = Depends(platform_admin),
                db: Session = Depends(get_db)):
    u = target_user(db, user_id)
    ratelimit.clear("login-fail:" + u.email)
    ratelimit.clear_prefix("login-try:" + u.email + "|")
    return act(db, request, user, "admin.unlock", u)


@router.post("/users/{user_id}/signout")
def user_signout(user_id: str, request: Request, user: models.User = Depends(platform_admin),
                 db: Session = Depends(get_db)):
    u = target_user(db, user_id)
    revoke_sessions(db, u)
    return act(db, request, user, "admin.signout", u)


@router.post("/users/{user_id}/verify")
def user_verify(user_id: str, request: Request, user: models.User = Depends(sudo_admin), db: Session = Depends(get_db)):
    u = target_user(db, user_id)
    mark_verified(db, u, "admin")
    return act(db, request, user, "admin.verify", u)


@router.post("/users/{user_id}/disabled")
def user_disabled(user_id: str, body: FlagIn, request: Request, user: models.User = Depends(sudo_admin),
                  db: Session = Depends(get_db)):
    u = target_user(db, user_id)
    if u.id == user.id:
        raise HTTPException(400, "you cannot disable your own account")
    u.disabled = body.on
    if body.on:
        revoke_sessions(db, u)
        revoke_credentials(db, u)
    return act(db, request, user, "admin.disable" if body.on else "admin.enable", u)


def admin_count(db):
    return db.scalar(select(func.count()).select_from(models.User).where(models.User.is_platform_admin.is_(True),
                                                                       models.User.disabled.is_(False))) or 0


@router.post("/users/{user_id}/admin")
def user_admin(user_id: str, body: FlagIn, request: Request, user: models.User = Depends(sudo_admin),
               db: Session = Depends(get_db)):
    u = target_user(db, user_id)
    if not body.on and u.is_platform_admin and admin_count(db) <= 1:
        raise HTTPException(400, "the server needs at least one platform administrator")
    if body.on and u.email_verified_at is None:
        raise HTTPException(400, "this account has not confirmed its email yet")
    u.is_platform_admin = body.on
    return act(db, request, user, "admin.grant" if body.on else "admin.revoke", u)


@router.delete("/users/{user_id}")
def user_delete(user_id: str, request: Request, user: models.User = Depends(sudo_admin), db: Session = Depends(get_db)):
    u = target_user(db, user_id)
    if u.id == user.id:
        raise HTTPException(400, "you cannot delete your own account here")
    if u.is_platform_admin and admin_count(db) <= 1:
        raise HTTPException(400, "the server needs at least one platform administrator")
    sole = []
    for m in db.scalars(select(models.Membership).where(models.Membership.user_id == u.id,
                                                        models.Membership.role == "owner")):
        owners = db.scalar(select(func.count()).select_from(models.Membership)
                           .where(models.Membership.org_id == m.org_id, models.Membership.role == "owner")) or 0
        if owners <= 1:
            sole.append(db.get(models.Organization, m.org_id).name)
    if sole:
        raise HTTPException(400, "this person is the only owner of %s; make someone else an owner first"
                            % ", ".join(sole))
    audit.log(db, "admin.delete_user", user, ip=client_ip(request), target=u.id, email=u.email)
    db.delete(u)
    db.commit()
    return {"ok": True}


@router.get("/orgs")
def list_orgs(q: str = "", offset: int = 0, limit: int = 50, user: models.User = Depends(platform_admin),
              db: Session = Depends(get_db)):
    offset, limit = page(offset, limit)
    stmt = select(models.Organization, models.District).join(models.District,
                                                            models.District.id == models.Organization.district_id)
    if q.strip():
        like = "%" + q.strip().lower() + "%"
        stmt = stmt.where(or_(func.lower(models.Organization.name).like(like),
                              func.lower(models.Organization.school).like(like),
                              func.lower(models.District.name).like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(models.Organization.created_at.desc()).offset(offset).limit(limit)).all()
    out = []
    for o, d in rows:
        owners = db.scalars(select(models.User.email).join(models.Membership, models.Membership.user_id == models.User.id)
                            .where(models.Membership.org_id == o.id, models.Membership.role == "owner")).all()
        out.append({"id": o.id, "name": o.name, "school": o.school, "school_id": o.school_id, "district": d.name,
                    "district_id": d.id, "created_at": o.created_at,
                    "owners": owners,
                    "members": db.scalar(select(func.count()).select_from(models.Membership)
                                         .where(models.Membership.org_id == o.id)) or 0,
                    "meetings": db.scalar(select(func.count()).select_from(models.Meeting)
                                          .where(models.Meeting.org_id == o.id)) or 0})
    return {"total": total, "orgs": out}


@router.get("/orgs/{org_id}")
def org_detail(org_id: str, user: models.User = Depends(platform_admin), db: Session = Depends(get_db)):
    o = db.get(models.Organization, org_id)
    if o is None:
        raise HTTPException(404, "organization not found")
    members = db.execute(select(models.Membership, models.User).join(models.User, models.User.id == models.Membership.user_id)
                         .where(models.Membership.org_id == o.id).order_by(models.User.email)).all()
    meetings = db.scalars(select(models.Meeting).where(models.Meeting.org_id == o.id)
                          .order_by(models.Meeting.created_at.desc()).limit(100)).all()
    return {"id": o.id, "name": o.name, "school": o.school, "school_id": o.school_id,
            "district": db.get(models.District, o.district_id).name,
            "created_at": o.created_at,
            "members": [{"membership_id": m.id, "user_id": u.id, "email": u.email, "name": u.name, "role": m.role}
                        for m, u in members],
            "meetings": [{"id": m.id, "title": m.title, "status": m.status, "created_at": m.created_at} for m in meetings]}


@router.post("/orgs/{org_id}/members")
def org_add_member(org_id: str, body: MemberIn, request: Request, user: models.User = Depends(platform_admin),
                   db: Session = Depends(get_db)):
    o = db.get(models.Organization, org_id)
    if o is None:
        raise HTTPException(404, "organization not found")
    if body.role not in models.ROLES:
        raise HTTPException(400, "unknown role")
    u = db.scalar(select(models.User).where(models.User.email == body.email.strip().lower()))
    if u is None or u.email_verified_at is None:
        raise HTTPException(400, "no confirmed account with that email; send them an invite instead")
    m = db.scalar(select(models.Membership).where(models.Membership.user_id == u.id, models.Membership.org_id == o.id))
    if m is None:
        db.add(models.Membership(user_id=u.id, org_id=o.id, role=body.role))
    else:
        m.role = body.role
    audit.log(db, "admin.add_member", user, o.id, client_ip(request), member=u.id, role=body.role)
    db.commit()
    return {"ok": True}


@router.delete("/orgs/{org_id}")
def org_delete(org_id: str, request: Request, user: models.User = Depends(sudo_admin), db: Session = Depends(get_db)):
    o = db.get(models.Organization, org_id)
    if o is None:
        raise HTTPException(404, "organization not found")
    governance.check_hold(db, o, "delete this organization")
    audit.log(db, "admin.delete_org", user, o.id, client_ip(request), name=o.name)
    governance.delete_org(db, o)
    db.commit()
    return {"ok": True}


@router.post("/personal-invites")
def personal_invite(body: PersonalInviteIn, request: Request, user: models.User = Depends(platform_admin),
                    db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if "@" not in email or len(email) > 320 or any(ch.isspace() for ch in email):
        raise HTTPException(400, "enter a valid email address")
    ratelimit.hit("personal-invite:" + user.id, 50, 86400, "you have sent many invites today; try again tomorrow")
    org = models.Organization(district_id=personal.district(db).id, school_id=None, school="",
                              name=personal.workspace_name(body.name), settings={})
    db.add(org)
    db.flush()
    token = new_token()
    days = int(runtime.get("invite_days"))
    link = settings.public_url + "/invite/" + token
    db.add(models.Invite(org_id=org.id, email=email, role="owner", token_hash=token_hash(token), created_by=user.id,
                         expires_at=time.time() + days * 86400))
    mailer.queue(db, email, "Your Live Minutes workspace",
                 "%s invited you to Live Minutes, which turns your meeting transcripts and chat into minutes.\n\n"
                 "Open this link to create your account and your own private workspace:\n\n%s\n\n"
                 "The link works for %d days." % (user.name or user.email, link, days))
    audit.log(db, "invite.personal", user, org.id, client_ip(request), email=email)
    db.commit()
    emailed = settings.mail_backend != "none"
    return {"link": "" if emailed else link, "email": email, "org_id": org.id, "emailed": emailed}


@router.get("/join-requests")
def all_join_requests(user: models.User = Depends(platform_admin), db: Session = Depends(get_db)):
    rows = db.execute(select(models.JoinRequest, models.User, models.Organization)
                      .join(models.User, models.User.id == models.JoinRequest.user_id)
                      .join(models.Organization, models.Organization.id == models.JoinRequest.org_id)
                      .where(models.JoinRequest.status == "pending")
                      .order_by(models.JoinRequest.created_at.desc()).limit(200)).all()
    return {"requests": [{"id": j.id, "org_id": o.id, "org": o.name, "school": o.school, "email": u.email,
                          "name": u.name, "school_email": j.school_email, "message": j.message,
                          "created_at": j.created_at} for j, u, o in rows]}


@router.get("/emails")
def emails(status: str = "", user: models.User = Depends(platform_admin), db: Session = Depends(get_db)):
    stmt = select(models.OutboxEmail)
    if status == "failed":
        stmt = stmt.where(models.OutboxEmail.sent_at.is_(None), models.OutboxEmail.attempts >= mailer.MAX_ATTEMPTS)
    elif status == "pending":
        stmt = stmt.where(models.OutboxEmail.sent_at.is_(None), models.OutboxEmail.attempts < mailer.MAX_ATTEMPTS)
    elif status == "sent":
        stmt = stmt.where(models.OutboxEmail.sent_at.is_not(None))
    rows = db.scalars(stmt.order_by(models.OutboxEmail.created_at.desc()).limit(200)).all()
    return {"emails": [{"id": e.id, "to": e.to_addr, "subject": e.subject, "created_at": e.created_at,
                        "sent_at": e.sent_at, "attempts": e.attempts, "error": e.error[:200],
                        "status": "sent" if e.sent_at else ("failed" if e.attempts >= mailer.MAX_ATTEMPTS else "pending")}
                       for e in rows]}


@router.post("/emails/{email_id}/retry")
def email_retry(email_id: str, request: Request, user: models.User = Depends(platform_admin),
                db: Session = Depends(get_db)):
    e = db.get(models.OutboxEmail, email_id)
    if e is None or e.sent_at is not None:
        raise HTTPException(404, "email not found or already sent")
    e.attempts, e.next_try_at, e.error = 0, time.time(), ""
    audit.log(db, "admin.email_retry", user, ip=client_ip(request), to=e.to_addr)
    db.commit()
    return {"ok": True}


@router.get("/security")
def security(user: models.User = Depends(platform_admin), db: Session = Depends(get_db)):
    since = time.time() - 86400
    by_email = db.execute(select(models.RateEvent.key, func.count(), func.max(models.RateEvent.created_at))
                          .where(models.RateEvent.key.like("login-fail:%"), models.RateEvent.created_at > since)
                          .group_by(models.RateEvent.key).order_by(func.count().desc()).limit(50)).all()
    by_ip = db.execute(select(models.RateEvent.key, func.count(), func.max(models.RateEvent.created_at))
                       .where(models.RateEvent.key.like("login-fail-ip:%"), models.RateEvent.created_at > since)
                       .group_by(models.RateEvent.key).order_by(func.count().desc()).limit(50)).all()
    emails = [k.split(":", 1)[1] for k, _, _ in by_email]
    known = {u.email: u.id for u in db.scalars(select(models.User).where(models.User.email.in_(emails)))}
    counts = fail_counts(db, emails)
    return {"settings": runtime.describe(),
            "failed_by_account": [{"email": k.split(":", 1)[1], "count": n, "last": t,
                                   "user_id": known.get(k.split(":", 1)[1]),
                                   "locked": locked(*counts.get(k.split(":", 1)[1], (0, 0)))} for k, n, t in by_email],
            "failed_by_network": [{"ip": k.split(":", 1)[1], "count": n, "last": t} for k, n, t in by_ip],
            "turnstile_configured": settings.turnstile_enabled, "mail": settings.mail_backend,
            "sso": [p["id"] for p in sso.configured()]}


@router.put("/settings")
def save_settings(body: SettingsIn, request: Request, user: models.User = Depends(sudo_admin),
                  db: Session = Depends(get_db)):
    changed = runtime.save(db, body.values, user.id)
    audit.log(db, "admin.settings", user, ip=client_ip(request), changes=changed)
    db.commit()
    runtime.invalidate()
    return {"settings": runtime.describe()}


@router.get("/audit")
def platform_audit(q: str = "", action: str = "", offset: int = 0, limit: int = 100,
                   user: models.User = Depends(platform_admin), db: Session = Depends(get_db)):
    offset, limit = page(offset, limit)
    stmt = (select(models.AuditEvent, models.User.email, models.Organization.name)
            .outerjoin(models.User, models.User.id == models.AuditEvent.user_id)
            .outerjoin(models.Organization, models.Organization.id == models.AuditEvent.org_id))
    if action.strip():
        stmt = stmt.where(models.AuditEvent.action.like(action.strip() + "%"))
    if q.strip():
        stmt = stmt.where(func.lower(models.User.email).like("%" + q.strip().lower() + "%"))
    rows = db.execute(stmt.order_by(models.AuditEvent.id.desc()).offset(offset).limit(limit)).all()
    return {"events": [{"at": e.created_at, "action": e.action, "user": email or "", "org": org or "", "ip": e.ip,
                        "detail": e.detail} for e, email, org in rows]}


class RoleIn(BaseModel):
    email: str
    scope: str
    target_id: str


@router.get("/roles")
def all_roles(user: models.User = Depends(platform_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(models.AdminRole).order_by(models.AdminRole.scope, models.AdminRole.created_at)).all()
    districts = db.scalars(select(models.District).order_by(models.District.name)).all()
    schools = db.scalars(select(models.School).order_by(models.School.name)).all()
    return {"roles": role_rows(db, rows),
            "districts": [{"id": d.id, "name": d.name, "staff_domains": d.staff_domains or []} for d in districts],
            "schools": [{"id": s.id, "name": s.name, "district_id": s.district_id, "staff_domains": s.staff_domains or []}
                        for s in schools]}


@router.post("/roles")
def add_role(body: RoleIn, request: Request, user: models.User = Depends(sudo_admin), db: Session = Depends(get_db)):
    if body.scope not in models.ADMIN_SCOPES:
        raise HTTPException(400, "choose district or college")
    target = db.get(models.District if body.scope == "district" else models.School, body.target_id)
    if target is None:
        raise HTTPException(404, "not found")
    role = grant_role(db, request, user, body.scope, target, body.email)
    return {"ok": True, "id": role.id}


@router.delete("/roles/{role_id}")
def remove_role(role_id: str, request: Request, user: models.User = Depends(sudo_admin), db: Session = Depends(get_db)):
    role = db.get(models.AdminRole, role_id)
    if role is None:
        raise HTTPException(404, "role not found")
    revoke_role(db, request, user, role)
    return {"ok": True}


class PlanIn(BaseModel):
    name: str
    description: str = ""
    price_cents: int
    interval: str = "month"
    seat_limit: int | None = None
    active: bool = True


class SubscriptionIn(BaseModel):
    plan_id: str
    scope: str
    target_id: str
    status: str = "active"
    seats: int | None = None
    price_cents: int | None = None
    renews_at: float | None = None
    notes: str = ""


class SubscriptionPatch(BaseModel):
    status: str | None = None
    seats: int | None = None
    price_cents: int | None = None
    renews_at: float | None = None
    notes: str | None = None


STATUSES = ("trial", "active", "past_due", "canceled")
BILL_SCOPES = {"district": models.District, "school": models.School, "org": models.Organization}


def clean_plan(body):
    if body.interval not in ("month", "year"):
        raise HTTPException(400, "billing interval must be month or year")
    if body.price_cents < 0 or body.price_cents > 100_000_000:
        raise HTTPException(400, "enter a price between $0 and $1,000,000")
    if body.seat_limit is not None and not 1 <= body.seat_limit <= 1_000_000:
        raise HTTPException(400, "seat limit must be at least 1")
    name = " ".join(body.name.split())[:120]
    if len(name) < 2:
        raise HTTPException(400, "name the plan")
    return name


def monthly(cents, interval):
    return cents / 12 if interval == "year" else cents


def seat_usage(db, scope_name, target_id):
    stmt = select(func.count(func.distinct(models.Membership.user_id))).join(
        models.Organization, models.Organization.id == models.Membership.org_id)
    if scope_name == "org":
        stmt = stmt.where(models.Organization.id == target_id)
    elif scope_name == "school":
        stmt = stmt.where(models.Organization.school_id == target_id)
    else:
        stmt = stmt.where(models.Organization.district_id == target_id)
    return db.scalar(stmt) or 0


@router.get("/billing")
def billing(user: models.User = Depends(platform_admin), db: Session = Depends(get_db)):
    plans = db.scalars(select(models.Plan).order_by(models.Plan.price_cents)).all()
    subs = db.scalars(select(models.Subscription).order_by(models.Subscription.created_at.desc())).all()
    plan_by_id = {p.id: p for p in plans}
    now = time.time()
    rows, mrr, by_plan = [], 0.0, {}
    counts = {s: 0 for s in STATUSES}
    for sub in subs:
        target = db.get(BILL_SCOPES[sub.scope], sub.target_id)
        counts[sub.status] = counts.get(sub.status, 0) + 1
        value = monthly(sub.price_cents, sub.interval)
        if sub.status in ("active", "past_due"):
            mrr += value
            by_plan[sub.plan_id] = by_plan.get(sub.plan_id, 0.0) + value
        rows.append({"id": sub.id, "plan_id": sub.plan_id, "plan": plan_by_id[sub.plan_id].name if sub.plan_id in plan_by_id else "",
                     "scope": sub.scope, "target_id": sub.target_id, "target": target.name if target else "(deleted)",
                     "status": sub.status, "seats": sub.seats, "used_seats": seat_usage(db, sub.scope, sub.target_id),
                     "price_cents": sub.price_cents, "interval": sub.interval, "monthly_cents": round(value),
                     "started_at": sub.started_at, "renews_at": sub.renews_at, "canceled_at": sub.canceled_at,
                     "notes": sub.notes})
    renewals = [r for r in rows if r["renews_at"] and now <= r["renews_at"] <= now + 30 * 86400 and r["status"] != "canceled"]
    return {"payments_connected": False,
            "summary": {"mrr_cents": round(mrr), "arr_cents": round(mrr * 12), "counts": counts,
                        "renewals_30d": len(renewals),
                        "renewals_30d_cents": sum(r["price_cents"] for r in renewals),
                        "by_plan": [{"plan": plan_by_id[k].name, "mrr_cents": round(v)} for k, v in by_plan.items() if k in plan_by_id]},
            "plans": [{"id": p.id, "name": p.name, "description": p.description, "price_cents": p.price_cents,
                       "interval": p.interval, "seat_limit": p.seat_limit, "active": p.active} for p in plans],
            "subscriptions": rows,
            "targets": {"district": [{"id": d.id, "name": d.name} for d in db.scalars(select(models.District).order_by(models.District.name))],
                        "school": [{"id": s.id, "name": s.name} for s in db.scalars(select(models.School).order_by(models.School.name))],
                        "org": [{"id": o.id, "name": o.name + (" · " + o.school if o.school else "")}
                                for o in db.scalars(select(models.Organization).order_by(models.Organization.name))]}}


@router.post("/plans")
def add_plan(body: PlanIn, request: Request, user: models.User = Depends(sudo_admin), db: Session = Depends(get_db)):
    plan = models.Plan(name=clean_plan(body), description=body.description.strip()[:500], price_cents=body.price_cents,
                       interval=body.interval, seat_limit=body.seat_limit, active=body.active)
    db.add(plan)
    audit.log(db, "billing.plan_added", user, ip=client_ip(request), plan=plan.name, price_cents=plan.price_cents)
    db.commit()
    return {"id": plan.id}


@router.patch("/plans/{plan_id}")
def edit_plan(plan_id: str, body: PlanIn, request: Request, user: models.User = Depends(sudo_admin),
              db: Session = Depends(get_db)):
    plan = db.get(models.Plan, plan_id)
    if plan is None:
        raise HTTPException(404, "plan not found")
    plan.name, plan.description = clean_plan(body), body.description.strip()[:500]
    plan.price_cents, plan.interval, plan.seat_limit, plan.active = body.price_cents, body.interval, body.seat_limit, body.active
    audit.log(db, "billing.plan_edited", user, ip=client_ip(request), plan=plan.name, price_cents=plan.price_cents)
    db.commit()
    return {"ok": True}


@router.post("/subscriptions")
def add_subscription(body: SubscriptionIn, request: Request, user: models.User = Depends(sudo_admin),
                     db: Session = Depends(get_db)):
    plan = db.get(models.Plan, body.plan_id)
    if plan is None:
        raise HTTPException(404, "plan not found")
    if body.scope not in BILL_SCOPES or db.get(BILL_SCOPES[body.scope], body.target_id) is None:
        raise HTTPException(400, "choose a district, college, or organization")
    if body.status not in STATUSES:
        raise HTTPException(400, "unknown status")
    price = plan.price_cents if body.price_cents is None else body.price_cents
    if price < 0:
        raise HTTPException(400, "price cannot be negative")
    sub = models.Subscription(plan_id=plan.id, scope=body.scope, target_id=body.target_id, status=body.status,
                              seats=body.seats or plan.seat_limit, price_cents=price, interval=plan.interval,
                              renews_at=body.renews_at, notes=body.notes.strip()[:500], created_by=user.id)
    db.add(sub)
    audit.log(db, "billing.subscription_added", user, ip=client_ip(request), plan=plan.name, scope=body.scope,
              target=body.target_id, price_cents=price, status=body.status)
    db.commit()
    return {"id": sub.id}


@router.patch("/subscriptions/{sub_id}")
def edit_subscription(sub_id: str, body: SubscriptionPatch, request: Request, user: models.User = Depends(sudo_admin),
                      db: Session = Depends(get_db)):
    sub = db.get(models.Subscription, sub_id)
    if sub is None:
        raise HTTPException(404, "subscription not found")
    if body.status is not None:
        if body.status not in STATUSES:
            raise HTTPException(400, "unknown status")
        sub.status = body.status
        sub.canceled_at = time.time() if body.status == "canceled" else None
    if body.seats is not None:
        sub.seats = body.seats
    if body.price_cents is not None:
        if body.price_cents < 0:
            raise HTTPException(400, "price cannot be negative")
        sub.price_cents = body.price_cents
    if body.renews_at is not None:
        sub.renews_at = body.renews_at
    if body.notes is not None:
        sub.notes = body.notes.strip()[:500]
    sub.updated_at = time.time()
    audit.log(db, "billing.subscription_edited", user, ip=client_ip(request), subscription=sub.id,
              status=sub.status, price_cents=sub.price_cents)
    db.commit()
    return {"ok": True}


class MergeIn(BaseModel):
    into_id: str


class OrgSchoolIn(BaseModel):
    school_id: str


@router.post("/districts/{district_id}/merge")
def merge_district(district_id: str, body: MergeIn, request: Request, user: models.User = Depends(sudo_admin),
                   db: Session = Depends(get_db)):
    source = db.get(models.District, district_id)
    target = db.get(models.District, body.into_id)
    if source is None or target is None or source.id == target.id:
        raise HTTPException(400, "choose two different districts")
    moved = {"schools": 0, "orgs": 0}
    targets = {s.slug: s for s in db.scalars(select(models.School).where(models.School.district_id == target.id))}
    for school in db.scalars(select(models.School).where(models.School.district_id == source.id)).all():
        same = targets.get(school.slug)
        if same is None:
            school.district_id = target.id
            moved["schools"] += 1
            continue
        same.email_domains = list(dict.fromkeys((same.email_domains or []) + (school.email_domains or [])))
        same.staff_domains = list(dict.fromkeys((same.staff_domains or []) + (school.staff_domains or [])))
        for org in db.scalars(select(models.Organization).where(models.Organization.school_id == school.id)):
            org.school_id, org.school = same.id, same.name
        for role in db.scalars(select(models.AdminRole).where(models.AdminRole.scope == "school",
                                                              models.AdminRole.target_id == school.id)):
            role.target_id = same.id
        for sub in db.scalars(select(models.Subscription).where(models.Subscription.scope == "school",
                                                                models.Subscription.target_id == school.id)):
            sub.target_id = same.id
        for h in db.scalars(select(models.LegalHold).where(models.LegalHold.scope == "school",
                                                           models.LegalHold.target_id == school.id)):
            h.target_id = same.id
        db.flush()
        db.delete(school)
    for org in db.scalars(select(models.Organization).where(models.Organization.district_id == source.id)):
        org.district_id = target.id
        moved["orgs"] += 1
    for role in db.scalars(select(models.AdminRole).where(models.AdminRole.scope == "district",
                                                          models.AdminRole.target_id == source.id)):
        role.target_id = target.id
    for sub in db.scalars(select(models.Subscription).where(models.Subscription.scope == "district",
                                                            models.Subscription.target_id == source.id)):
        sub.target_id = target.id
    for req in db.scalars(select(models.SchoolRequest).where(models.SchoolRequest.district_id == source.id)):
        req.district_id, req.district_name = target.id, target.name
    target.staff_domains = list(dict.fromkeys((target.staff_domains or []) + (source.staff_domains or [])))
    governance.move_holds(db, source, target)
    audit.log(db, "district.merged", user, ip=client_ip(request), source=source.name, into=target.name, **moved)
    db.flush()
    db.delete(source)
    db.commit()
    return {"ok": True, **moved}


@router.patch("/orgs/{org_id}/school")
def move_org(org_id: str, body: OrgSchoolIn, request: Request, user: models.User = Depends(sudo_admin),
             db: Session = Depends(get_db)):
    org = db.get(models.Organization, org_id)
    school = db.get(models.School, body.school_id)
    if org is None or school is None:
        raise HTTPException(404, "not found")
    clash = db.scalar(select(models.Organization).where(models.Organization.school_id == school.id,
                                                        func.lower(models.Organization.name) == org.name.lower(),
                                                        models.Organization.id != org.id))
    if clash is not None:
        raise HTTPException(409, "%s already has an organization named %s" % (school.name, org.name))
    org.school_id, org.school, org.district_id = school.id, school.name, school.district_id
    audit.log(db, "org.moved", user, org.id, client_ip(request), school=school.name)
    db.commit()
    return {"ok": True}
