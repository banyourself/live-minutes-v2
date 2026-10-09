import time

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, officers, runtime, scope
from .db import get_db
from .security import token_hash
from .settings import settings

TOUCH_EVERY = 300
MAINTENANCE = "Live Minutes is down for maintenance; try again soon"
SUDO = "confirm your password to continue"


def host_cookie(base):
    return "__Host-" + base if settings.secure_cookies else base


def scoped_cookie(base):
    return "__Secure-" + base if settings.secure_cookies else base


def session_cookie():
    return host_cookie("lm_session")


def _session_user(request, db):
    token = request.cookies.get(session_cookie(), "")
    auth = request.headers.get("Authorization", "")
    if not token and auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        raise HTTPException(401, "sign in required")
    sess = db.scalar(select(models.UserSession).where(models.UserSession.token_hash == token_hash(token)))
    now = time.time()
    if sess is None or sess.expires_at < now:
        raise HTTPException(401, "session expired; sign in again")
    seen = sess.last_seen_at or sess.created_at
    if now - seen > float(runtime.get("session_idle_hours")) * 3600:
        db.delete(sess)
        db.commit()
        raise HTTPException(401, "signed out after a period of inactivity; sign in again")
    user = db.get(models.User, sess.user_id)
    if user is None or user.disabled:
        raise HTTPException(401, "sign in required")
    if runtime.get("maintenance_mode") and not user.is_platform_admin:
        raise HTTPException(503, MAINTENANCE)
    if now - seen > TOUCH_EVERY:
        sess.last_seen_at = now
        db.commit()
    request.state.user = user
    request.state.session_id = sess.id
    request.state.sudo_until = sess.sudo_until or 0.0
    return user


def any_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    return _session_user(request, db)


def current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    user = _session_user(request, db)
    if user.email_verified_at is None:
        raise HTTPException(403, "verify your email address first; check your inbox for the link")
    return user


def platform_admin(user: models.User = Depends(current_user)) -> models.User:
    if not user.is_platform_admin:
        raise HTTPException(403, "this needs a platform administrator")
    return user


def sudo_admin(request: Request, user: models.User = Depends(platform_admin)) -> models.User:
    if getattr(request.state, "sudo_until", 0.0) < time.time():
        raise HTTPException(403, SUDO)
    return user


def sudo_user(request: Request, user: models.User = Depends(current_user)) -> models.User:
    if getattr(request.state, "sudo_until", 0.0) < time.time():
        raise HTTPException(403, SUDO)
    return user


def membership(db, user, org_id):
    return db.scalar(select(models.Membership).where(
        models.Membership.user_id == user.id, models.Membership.org_id == org_id))


def require_role(db, user, org_id, minimum="viewer"):
    org = db.get(models.Organization, org_id)
    if org is None:
        raise HTTPException(404, "organization not found")
    if user.is_platform_admin:
        return org, "owner"
    m = membership(db, user, org_id)
    role = officers.effective_role(db, m) if m is not None else None
    if role is not None and models.ROLE_RANK[role] >= models.ROLE_RANK[minimum]:
        return org, role
    if scope.covers_org(db, user, org):
        return org, "owner"
    if m is None:
        raise HTTPException(404, "organization not found")
    raise HTTPException(403, "this needs the %s role or higher" % minimum)


def meeting_for(db, user, meeting_id, minimum="viewer"):
    mt = db.get(models.Meeting, meeting_id)
    if mt is None:
        raise HTTPException(404, "meeting not found")
    org, role = require_role(db, user, mt.org_id, minimum)
    return mt, org, role


def client_ip(request: Request):
    peer = request.client.host if request.client else ""
    hops = settings.trusted_proxy_hops
    if hops > 0:
        chain = [p.strip() for p in request.headers.get("X-Forwarded-For", "").split(",") if p.strip()]
        if len(chain) >= hops:
            peer = chain[-hops]
    return peer[:64]
