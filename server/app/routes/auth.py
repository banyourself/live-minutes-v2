import json
import time
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .. import (audit, captcha, mailer, models, officers, personal, ratelimit, runtime, school_sso, scope, sso, twofactor,
               validation)
from ..db import get_db
from ..deps import MAINTENANCE, _session_user, any_user, client_ip, current_user, scoped_cookie, session_cookie, sudo_user
from ..security import burn_password_check, decrypt, encrypt, hash_password, new_token, token_hash, verify_password
from ..settings import settings

TERMS_VERSION = "2026-10-08"
router = APIRouter(prefix="/api/auth", tags=["auth"])
CHECK_EMAIL = {"ok": True, "status": "check_email"}
LINK_MINUTES = 10
SUDO_MINUTES = 10
SECOND_STEP_SECONDS = 300
SECOND_STEP_COOKIE = "lm_2fa"


class SignupIn(BaseModel):
    email: str
    password: str
    name: str = ""
    account_type: str = ""
    invite_token: str = ""
    captcha: str = ""
    accept_terms: bool = False


class TypeIn(BaseModel):
    account_type: str


class LoginIn(BaseModel):
    email: str
    password: str
    captcha: str = ""


class EmailIn(BaseModel):
    email: str
    captcha: str = ""


class TokenIn(BaseModel):
    token: str
    password: str = ""


class ResetIn(BaseModel):
    token: str
    password: str


class SudoIn(BaseModel):
    password: str


class PasswordIn(BaseModel):
    current: str = ""
    new: str


class CodeIn(BaseModel):
    code: str


def norm_email(raw):
    return validation.clean_email(raw)


def check_password(password, email="", name=""):
    validation.check_password(password, email, name)


def start_session(db, user, response, request):
    token = new_token()
    now = time.time()
    days = int(runtime.get("session_days"))
    db.add(models.UserSession(user_id=user.id, token_hash=token_hash(token), last_seen_at=now,
                              expires_at=now + days * 86400,
                              user_agent=request.headers.get("User-Agent", "")[:300]))
    user.last_login_at = now
    response.set_cookie(session_cookie(), token, httponly=True, samesite="lax", secure=settings.secure_cookies,
                        max_age=days * 86400, path="/")
    return token


def security_mail(db, user, subject, what):
    mailer.queue(db, user.email, subject,
                 "%s\n\nIf this was not you, reset your password right away at %s/login, then check Security under My "
                 "account." % (what, settings.public_url))


def second_step(db, user, response, request, next_url="/dashboard"):
    response.set_cookie(scoped_cookie(SECOND_STEP_COOKIE),
                        encrypt(json.dumps({"u": user.id, "t": time.time(), "n": new_token(), "x": next_url})),
                        httponly=True, samesite="lax", secure=settings.secure_cookies, max_age=SECOND_STEP_SECONDS,
                        path="/api/auth")
    audit.log(db, "user.login_second_step", user, ip=client_ip(request))


def revoke_credentials(db, user):
    db.execute(delete(models.OAuthCode).where(models.OAuthCode.user_id == user.id))
    db.execute(delete(models.PersonalToken).where(models.PersonalToken.user_id == user.id))
    db.execute(delete(models.CalendarFeed).where(models.CalendarFeed.user_id == user.id))
    db.execute(update(models.CaptureToken).where(models.CaptureToken.user_id == user.id).values(revoked=True))


def revoke_sessions(db, user, keep=None):
    stmt = delete(models.UserSession).where(models.UserSession.user_id == user.id)
    if keep:
        stmt = stmt.where(models.UserSession.id != keep)
    db.execute(stmt)


def mark_verified(db, user, via, trusted=True, admin_ok=True):
    if not trusted:
        return
    if user.email_verified_at is None:
        user.email_verified_at, user.verified_via = time.time(), via
    if user.account_type == "personal":
        personal.ensure_workspace(db, user)
    if via in ("link", "sso") and admin_ok and user.email in settings.platform_admins and not user.is_platform_admin:
        user.is_platform_admin = True
        audit.log(db, "user.platform_admin", user)


def cancel_links(db, user, purpose):
    db.execute(update(models.EmailToken).where(models.EmailToken.user_id == user.id,
                                               models.EmailToken.purpose == purpose,
                                               models.EmailToken.used_at.is_(None)).values(used_at=time.time()))


def issue_token(db, user, purpose, minutes=LINK_MINUTES):
    cancel_links(db, user, purpose)
    raw = new_token()
    db.add(models.EmailToken(user_id=user.id, purpose=purpose, token_hash=token_hash(raw),
                             expires_at=time.time() + minutes * 60))
    return raw


def use_token(db, raw, purpose):
    tok = db.scalar(select(models.EmailToken).where(models.EmailToken.token_hash == token_hash(raw or ""),
                                                    models.EmailToken.purpose == purpose))
    if tok is None or tok.used_at is not None or tok.expires_at < time.time():
        raise HTTPException(400, "this link is invalid or has expired; request a new one")
    user = db.get(models.User, tok.user_id)
    if user is None or user.disabled:
        raise HTTPException(400, "this link is invalid or has expired; request a new one")
    tok.used_at = time.time()
    return user


def send_verify(db, user):
    raw = issue_token(db, user, "verify")
    mailer.queue(db, user.email, "Confirm your email for Live Minutes",
                 "Open this link to confirm your email address and finish setting up Live Minutes:\n\n"
                 "%s/verify/%s\n\nThe link works for %d minutes and only once. If it expires, sign in and ask for a new one. "
                 "If you did not sign up, ignore this email." % (settings.public_url, raw, LINK_MINUTES))


def send_reset(db, user):
    raw = issue_token(db, user, "reset")
    mailer.queue(db, user.email, "Reset your Live Minutes password",
                 "Open this link to choose a new password:\n\n%s/reset/%s\n\n"
                 "The link works for %d minutes and only once, and it signs you out everywhere else. Asking for "
                 "another link cancels this one. If you did not ask for this, ignore this email."
                 % (settings.public_url, raw, LINK_MINUTES))


def invite_by_token(db, raw):
    inv = db.scalar(select(models.Invite).where(models.Invite.token_hash == token_hash(raw or "")))
    if inv is None or inv.accepted_at is not None or (inv.expires_at and inv.expires_at < time.time()):
        return None
    return inv


def accept_invite(db, user, inv):
    if inv.email.lower() != user.email.lower():
        raise HTTPException(403, "this invite was sent to a different email address")
    exists = db.scalar(select(models.Membership).where(models.Membership.user_id == user.id,
                                                       models.Membership.org_id == inv.org_id))
    if exists is None:
        db.add(models.Membership(user_id=user.id, org_id=inv.org_id, role=inv.role))
    inv.accepted_at = time.time()
    return inv


def domain_allowed(db, email):
    domain = email.rsplit("@", 1)[-1]
    for d in db.scalars(select(models.District)).all():
        if domain in [x.lower() for x in (d.allowed_domains or [])]:
            return True
    return False


def pending_invite(db, email):
    return db.scalar(select(models.Invite).where(models.Invite.email == email,
                                                 models.Invite.accepted_at.is_(None),
                                                 (models.Invite.expires_at.is_(None)) |
                                                 (models.Invite.expires_at > time.time()))) is not None


@router.post("/signup")
def signup(body: SignupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ratelimit.hit("signup-ip:" + client_ip(request), 40, 3600)
    captcha.verify(body.captcha, client_ip(request), "signup")
    if body.account_type not in models.ACCOUNT_TYPES:
        raise HTTPException(400, "choose whether you are a student, faculty, staff, or IT")
    if not body.accept_terms:
        raise HTTPException(400, "agree to the Terms of use and Privacy policy to create an account")
    email = norm_email(body.email)
    check_password(body.password, email, body.name)
    inv = invite_by_token(db, body.invite_token) if body.invite_token else None
    if body.invite_token and (inv is None or inv.email.lower() != email):
        raise HTTPException(400, "this invite link is invalid, expired, or for a different email address")
    if body.account_type == "personal" and not (personal.is_personal(db, inv.org_id) if inv else personal.open_signup()):
        raise HTTPException(400, "choose whether you are a student, faculty, staff, or IT")
    if not (runtime.get("allow_signup") or inv or domain_allowed(db, email)):
        raise HTTPException(403, "sign-up is by invitation on this server")
    existing = db.scalar(select(models.User).where(models.User.email == email))
    if existing is not None:
        burn_password_check(body.password)
        if ratelimit.blocked("signup-email:" + email, 3, 86400):
            return CHECK_EMAIL
        ratelimit.record("signup-email:" + email)
        mailer.queue(db, email, "Your Live Minutes account",
                     "Someone tried to create a Live Minutes account with this email address, but one already "
                     "exists. If it was you, sign in at %s/login or reset your password from that page."
                     % settings.public_url)
        db.commit()
        return CHECK_EMAIL
    user = models.User(email=email, name=body.name.strip()[:200], password_hash=hash_password(body.password),
                       password_changed_at=time.time(), account_type=body.account_type,
                       terms_version=TERMS_VERSION, terms_accepted_at=time.time())
    db.add(user)
    db.flush()
    audit.log(db, "user.signup", user, ip=client_ip(request))
    if inv is not None:
        accept_invite(db, user, inv)
    send_verify(db, user)
    db.commit()
    return CHECK_EMAIL


def try_key(email, ip):
    return "login-try:" + email + "|" + ip


def login_locked(email, ip):
    if not captcha.required() and ratelimit.blocked("login-fail:" + email, int(runtime.get("lock_day")) * 5, 86400):
        return "this account is locked after too many failed sign-ins; reset your password to unlock it"
    if ratelimit.blocked(try_key(email, ip), int(runtime.get("lock_day")), 86400):
        return "too many failed sign-ins for this account from your network today; reset your password to unlock it"
    if ratelimit.blocked(try_key(email, ip), int(runtime.get("lock_short")), 900):
        return "too many failed sign-ins for this account; wait 15 minutes or reset your password"
    if ratelimit.blocked("login-fail-ip:" + ip, 30, 600):
        return "too many failed sign-ins from your network; wait 10 minutes and try again"
    return ""


def warn_owner(db, user):
    if user is None or ratelimit.blocked("login-warn:" + user.id, 1, 3600):
        return
    ratelimit.record("login-warn:" + user.id)
    mailer.queue(db, user.email, "Failed sign-ins to your Live Minutes account",
                 "Someone has tried several wrong passwords for your Live Minutes account. If it was not you, "
                 "your account is still safe, but you can reset your password at %s/login. Sign-ins for this "
                 "account are paused for 15 minutes." % settings.public_url)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    ratelimit.hit("login-ip:" + ip, 120, 600)
    captcha.verify(body.captcha, ip, "login")
    email = (body.email or "").strip().lower()[:320]
    fail_key = "login-fail:" + email
    locked = login_locked(email, ip)
    if locked:
        burn_password_check(body.password)
        raise HTTPException(429, locked)
    user = db.scalar(select(models.User).where(models.User.email == email))
    if user is None or not user.password_hash:
        ok = burn_password_check(body.password)
    else:
        ok = verify_password(body.password, user.password_hash) and not user.disabled
    if not ok:
        ratelimit.record(fail_key)
        ratelimit.record(try_key(email, ip))
        ratelimit.record("login-fail-ip:" + ip)
        audit.log(db, "user.login_failed", user if user is not None else None, ip=ip)
        if ratelimit.blocked(fail_key, int(runtime.get("lock_short")), 900):
            warn_owner(db, user)
        db.commit()
        raise HTTPException(401, "email or password is incorrect")
    if runtime.get("maintenance_mode") and not user.is_platform_admin:
        raise HTTPException(503, MAINTENANCE)
    if user.totp_enabled_at:
        second_step(db, user, response, request)
        db.commit()
        return {"ok": True, "status": "two_factor"}
    start_session(db, user, response, request)
    audit.log(db, "user.login", user, ip=ip)
    db.commit()
    ratelimit.clear(fail_key)
    ratelimit.clear(try_key(email, ip))
    return me_payload(db, user)


@router.post("/login/two-factor")
def login_two_factor(body: CodeIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    ratelimit.hit("2fa-ip:" + ip, 30, 900)
    try:
        saved = json.loads(decrypt(request.cookies.get(scoped_cookie(SECOND_STEP_COOKIE), "")))
    except (ValueError, json.JSONDecodeError):
        saved = {}
    user = db.get(models.User, saved.get("u", "")) if saved.get("u") else None
    if (user is None or user.disabled or not user.totp_enabled_at
            or time.time() - saved.get("t", 0) > SECOND_STEP_SECONDS
            or ratelimit.blocked("2fa-used:" + saved.get("n", ""), 1, 900)):
        raise HTTPException(400, "your sign-in expired; enter your email and password again")
    fail = "2fa-fail:" + user.id
    if ratelimit.blocked(fail, 5, 900):
        raise HTTPException(429, "too many wrong codes; wait 15 minutes, then sign in again")
    method = twofactor.check(user, body.code)
    if method is None:
        ratelimit.record(fail)
        audit.log(db, "user.second_step_failed", user, ip=ip)
        db.commit()
        raise HTTPException(401, "that code is not right")
    if runtime.get("maintenance_mode") and not user.is_platform_admin:
        raise HTTPException(503, MAINTENANCE)
    ratelimit.record("2fa-used:" + saved["n"])
    start_session(db, user, response, request)
    if method == "recovery":
        security_mail(db, user, "A Live Minutes recovery code was used",
                      "Someone signed in to your Live Minutes account with a recovery code. %d recovery codes are left."
                      % len(user.recovery_codes or []))
    audit.log(db, "user.login", user, ip=ip, second_step=method)
    db.commit()
    response.delete_cookie(scoped_cookie(SECOND_STEP_COOKIE), path="/api/auth", secure=settings.secure_cookies,
                           httponly=True, samesite="lax")
    ratelimit.clear(fail)
    ratelimit.clear("login-fail:" + user.email)
    ratelimit.clear(try_key(user.email, ip))
    return dict(me_payload(db, user), next=safe_next(saved.get("x") or "/dashboard"))


@router.post("/two-factor/setup")
def two_factor_setup(request: Request, user: models.User = Depends(sudo_user), db: Session = Depends(get_db)):
    if user.totp_enabled_at:
        raise HTTPException(400, "two-step sign-in is already on")
    secret = twofactor.new_secret()
    user.totp_pending_enc = encrypt(secret)
    db.commit()
    return {"secret": secret, "uri": twofactor.uri(user.email, secret)}


@router.post("/two-factor/enable")
def two_factor_enable(body: CodeIn, request: Request, user: models.User = Depends(current_user),
                      db: Session = Depends(get_db)):
    ratelimit.hit("2fa-enable:" + user.id, 10, 900)
    if user.totp_enabled_at:
        raise HTTPException(400, "two-step sign-in is already on")
    if not user.totp_pending_enc:
        raise HTTPException(400, "start setting up two-step sign-in again")
    secret = decrypt(user.totp_pending_enc)
    step = twofactor.matching_step(secret, body.code)
    if step is None:
        raise HTTPException(400, "that code is not right; check that your phone's clock is set automatically")
    plain, hashes = twofactor.new_recovery_codes()
    user.totp_secret_enc, user.totp_pending_enc, user.totp_enabled_at = encrypt(secret), "", time.time()
    user.totp_last_step, user.recovery_codes = step, hashes
    revoke_sessions(db, user, keep=getattr(request.state, "session_id", None))
    audit.log(db, "user.two_factor_on", user, ip=client_ip(request))
    security_mail(db, user, "Two-step sign-in is on for Live Minutes",
                  "Two-step sign-in was turned on for your Live Minutes account. Other devices were signed out.")
    db.commit()
    return {"recovery_codes": plain}


@router.post("/two-factor/disable")
def two_factor_disable(body: CodeIn, request: Request, user: models.User = Depends(sudo_user),
                       db: Session = Depends(get_db)):
    ratelimit.hit("2fa-disable:" + user.id, 10, 900)
    if not user.totp_enabled_at:
        return me_payload(db, user)
    if twofactor.check(user, body.code) is None:
        db.commit()
        raise HTTPException(400, "that code is not right")
    twofactor.clear(user)
    audit.log(db, "user.two_factor_off", user, ip=client_ip(request))
    security_mail(db, user, "Two-step sign-in is off for Live Minutes",
                  "Two-step sign-in was turned off for your Live Minutes account.")
    db.commit()
    return me_payload(db, user)


@router.post("/two-factor/recovery-codes")
def two_factor_recovery_codes(body: CodeIn, request: Request, user: models.User = Depends(sudo_user),
                              db: Session = Depends(get_db)):
    ratelimit.hit("2fa-codes:" + user.id, 10, 900)
    if not user.totp_enabled_at:
        raise HTTPException(400, "turn on two-step sign-in first")
    if twofactor.check(user, body.code) is None:
        db.commit()
        raise HTTPException(400, "that code is not right")
    plain, hashes = twofactor.new_recovery_codes()
    user.recovery_codes = hashes
    audit.log(db, "user.recovery_codes", user, ip=client_ip(request))
    security_mail(db, user, "New Live Minutes recovery codes",
                  "New recovery codes were made for your Live Minutes account. The old ones no longer work.")
    db.commit()
    return {"recovery_codes": plain}


@router.get("/sessions")
def list_sessions(request: Request, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(models.UserSession).where(models.UserSession.user_id == user.id)
                      .order_by(models.UserSession.created_at.desc())).all()
    current = getattr(request.state, "session_id", None)
    return {"sessions": [{"id": s.id, "user_agent": s.user_agent, "created_at": s.created_at,
                          "last_seen_at": s.last_seen_at, "current": s.id == current} for s in rows]}


@router.delete("/sessions/{session_id}")
def end_session(session_id: str, request: Request, user: models.User = Depends(current_user),
                db: Session = Depends(get_db)):
    row = db.get(models.UserSession, session_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "session not found")
    db.delete(row)
    audit.log(db, "user.session_ended", user, ip=client_ip(request))
    db.commit()
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(session_cookie(), "")
    if token:
        db.execute(delete(models.UserSession).where(models.UserSession.token_hash == token_hash(token)))
        db.commit()
    response.delete_cookie(session_cookie(), path="/", secure=settings.secure_cookies, httponly=True, samesite="lax")
    return {"ok": True}


@router.post("/logout-all")
def logout_all(request: Request, response: Response, user: models.User = Depends(any_user),
               db: Session = Depends(get_db)):
    revoke_sessions(db, user)
    audit.log(db, "user.logout_all", user, ip=client_ip(request))
    db.commit()
    response.delete_cookie(session_cookie(), path="/", secure=settings.secure_cookies, httponly=True, samesite="lax")
    return {"ok": True}


@router.post("/verify")
def verify(body: TokenIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ratelimit.hit("verify-ip:" + client_ip(request), 30, 3600)
    user = use_token(db, body.token, "verify")
    try:
        signed_in = _session_user(request, db)
    except HTTPException:
        signed_in = None
    keep = None
    if signed_in is not None and signed_in.id == user.id:
        keep = getattr(request.state, "session_id", None)
    elif not (body.password and user.password_hash and verify_password(body.password, user.password_hash)):
        burn_password_check(body.password or "x")
        raise HTTPException(409, "enter the password you chose when you signed up to finish confirming your email")
    mark_verified(db, user, "link")
    revoke_sessions(db, user, keep=keep)
    audit.log(db, "user.verified", user, ip=client_ip(request))
    if keep is None and user.totp_enabled_at:
        db.commit()
        return {"ok": True, "status": "sign_in"}
    if keep is None:
        start_session(db, user, response, request)
    db.commit()
    return me_payload(db, user)


@router.post("/verify/resend")
def verify_resend(request: Request, user: models.User = Depends(any_user), db: Session = Depends(get_db)):
    if user.email_verified_at is not None:
        return {"ok": True, "status": "verified"}
    ratelimit.hit("verify-resend:" + user.id, 3, 3600, "a link was sent recently; check your inbox and spam folder")
    send_verify(db, user)
    db.commit()
    return CHECK_EMAIL


@router.post("/forgot")
def forgot(body: EmailIn, request: Request, db: Session = Depends(get_db)):
    ratelimit.hit("forgot-ip:" + client_ip(request), 10, 3600)
    captcha.verify(body.captcha, client_ip(request), "forgot")
    email = validation.clean_email(body.email, check_dns=False)
    user = db.scalar(select(models.User).where(models.User.email == email))
    if user is not None and not user.disabled and not ratelimit.blocked("forgot:" + email, 3, 3600):
        ratelimit.record("forgot:" + email)
        send_reset(db, user)
        audit.log(db, "user.reset_requested", user, ip=client_ip(request))
        db.commit()
    return CHECK_EMAIL


@router.post("/reset")
def reset(body: ResetIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ratelimit.hit("reset-ip:" + client_ip(request), 20, 3600)
    user = use_token(db, body.token, "reset")
    check_password(body.password, user.email, user.name)
    user.password_hash, user.password_changed_at = hash_password(body.password), time.time()
    mark_verified(db, user, "link")
    revoke_sessions(db, user)
    revoke_credentials(db, user)
    cancel_links(db, user, "reset")
    audit.log(db, "user.password_reset", user, ip=client_ip(request))
    security_mail(db, user, "Your Live Minutes password was reset",
                  "The password for your Live Minutes account was just reset, and every device was signed out.")
    if not user.totp_enabled_at:
        start_session(db, user, response, request)
    db.commit()
    ratelimit.clear("login-fail:" + user.email)
    ratelimit.clear_prefix("login-try:" + user.email + "|")
    if user.totp_enabled_at:
        return {"ok": True, "status": "sign_in"}
    return me_payload(db, user)


@router.post("/password")
def change_password(body: PasswordIn, request: Request, user: models.User = Depends(current_user),
                    db: Session = Depends(get_db)):
    ratelimit.hit("password:" + user.id, 10, 3600)
    if not user.password_hash:
        raise HTTPException(400, "use the emailed link to set a password for this account")
    if not verify_password(body.current, user.password_hash):
        raise HTTPException(400, "your current password is incorrect")
    check_password(body.new, user.email, user.name)
    user.password_hash, user.password_changed_at = hash_password(body.new), time.time()
    revoke_sessions(db, user, keep=getattr(request.state, "session_id", None))
    revoke_credentials(db, user)
    cancel_links(db, user, "reset")
    audit.log(db, "user.password_changed", user, ip=client_ip(request))
    security_mail(db, user, "Your Live Minutes password was changed",
                  "The password for your Live Minutes account was just changed, and your other devices were signed out.")
    db.commit()
    return {"ok": True}


@router.post("/password-link")
def password_link(request: Request, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if user.password_hash:
        raise HTTPException(400, "change your password with your current one instead")
    ratelimit.hit("password-link:" + user.id, 3, 3600, "a link was sent recently; check your inbox")
    send_reset(db, user)
    audit.log(db, "user.password_link", user, ip=client_ip(request))
    db.commit()
    return CHECK_EMAIL


@router.post("/sudo")
def sudo(body: SudoIn, request: Request, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ratelimit.hit("sudo:" + user.id, 5, 900, "too many tries; wait 15 minutes")
    if not user.password_hash:
        raise HTTPException(400, "set a password under My account first")
    if not verify_password(body.password, user.password_hash):
        audit.log(db, "user.sudo_failed", user, ip=client_ip(request))
        db.commit()
        raise HTTPException(400, "that password is not right")
    sess = db.get(models.UserSession, request.state.session_id)
    sess.sudo_until = time.time() + SUDO_MINUTES * 60
    audit.log(db, "user.sudo", user, ip=client_ip(request))
    db.commit()
    return {"until": sess.sudo_until}


def me_payload(db, user):
    rows = db.execute(select(models.Membership, models.Organization, models.District)
                      .join(models.Organization, models.Organization.id == models.Membership.org_id)
                      .join(models.District, models.District.id == models.Organization.district_id)
                      .where(models.Membership.user_id == user.id)).all()
    verified = user.email_verified_at is not None
    return {"user": {"id": user.id, "email": user.email, "name": user.name, "account_type": user.account_type,
                     "is_platform_admin": user.is_platform_admin, "verified": verified,
                     "has_password": bool(user.password_hash),
                     "can_create_district": verified and (runtime.get("allow_district_creation") or user.is_platform_admin),
                     "admin_scopes": scope.scopes(db, user) if verified else [],
                     "idle_hours": float(runtime.get("session_idle_hours")),
                     "terms_current": user.terms_version == TERMS_VERSION, "terms_version": TERMS_VERSION,
                     "two_factor": bool(user.totp_enabled_at), "recovery_codes_left": len(user.recovery_codes or []),
                     "personal_open": personal.open_signup()},
            "orgs": [{"id": o.id, "name": o.name, "school": o.school, "district": d.name,
                      "district_id": d.id, "personal": personal.is_personal_district(d),
                      "role": officers.effective_role(db, m)} for m, o, d in rows]
            if verified else []}


@router.post("/accept-terms")
def accept_terms(request: Request, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    user.terms_version, user.terms_accepted_at = TERMS_VERSION, time.time()
    audit.log(db, "user.accepted_terms", user, ip=client_ip(request), version=TERMS_VERSION)
    db.commit()
    return me_payload(db, user)


TYPE_WORD = {"student": "student", "faculty": "work", "staff": "work", "it": "work"}
TYPE_NAME = {"student": "Student", "faculty": "Faculty", "staff": "Staff", "it": "IT", "personal": "Personal use"}


def proven_types(db, user):
    from .directory import expected_domains
    domains = set(db.scalars(select(models.SchoolEmail.domain).where(models.SchoolEmail.user_id == user.id,
                                                                     models.SchoolEmail.verified_at.is_not(None))).all())
    if user.email_verified_at is not None:
        domains.add(validation.email_domain(user.email))
    schools = db.scalars(select(models.School).where(models.School.active.is_(True))).all() if domains else []
    found = {user.account_type} if user.account_type else set()
    for kind in TYPE_WORD:
        if any(domains.intersection(expected_domains(s, kind)) for s in schools):
            found.add(kind)
    if personal.open_signup() or personal.has_workspace(db, user):
        found.add("personal")
    return found


def type_problem(db, user, kind):
    if not user.account_type or kind == user.account_type or kind in proven_types(db, user):
        return ""
    if kind == "personal":
        return "personal workspaces are by invitation on this server"
    return ("to switch to %s, first confirm your %s email from your college under School and work emails, then save "
            "again" % (TYPE_NAME[kind], TYPE_WORD[kind]))


@router.get("/account-type")
def account_type_options(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    allowed = proven_types(db, user) if user.account_type else set(models.ACCOUNT_TYPES)
    return {"current": user.account_type, "allowed": [t for t in models.ACCOUNT_TYPES if t in allowed],
            "needs": TYPE_WORD}


@router.post("/account-type")
def set_account_type(body: TypeIn, request: Request, user: models.User = Depends(current_user),
                     db: Session = Depends(get_db)):
    if body.account_type not in models.ACCOUNT_TYPES:
        raise HTTPException(400, "choose student, faculty, staff, or IT")
    if body.account_type == user.account_type:
        return me_payload(db, user)
    if body.account_type == "personal" and not (personal.open_signup() or personal.has_workspace(db, user)):
        raise HTTPException(400, "personal workspaces are by invitation on this server")
    problem = type_problem(db, user, body.account_type)
    if problem:
        raise HTTPException(400, problem)
    removed = 0
    if body.account_type not in models.IT_TYPES:
        for role in db.scalars(select(models.AdminRole).where(models.AdminRole.user_id == user.id)).all():
            db.delete(role)
            removed += 1
    audit.log(db, "user.account_type", user, ip=client_ip(request), before=user.account_type,
              after=body.account_type, roles_removed=removed)
    user.account_type = body.account_type
    if body.account_type == "personal" and user.email_verified_at is not None:
        personal.ensure_workspace(db, user)
    db.commit()
    return me_payload(db, user)


@router.post("/personal-workspace")
def personal_workspace(request: Request, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ratelimit.hit("personal-workspace:" + user.id, 5, 86400, "try again tomorrow")
    if user.account_type != "personal":
        raise HTTPException(400, "switch your account type to Personal under My account first")
    if not (personal.open_signup() or personal.has_workspace(db, user)):
        raise HTTPException(403, "personal workspaces are by invitation on this server")
    if personal.ensure_workspace(db, user) is not None:
        db.commit()
    return me_payload(db, user)


@router.get("/me")
def me(user: models.User = Depends(any_user), db: Session = Depends(get_db)):
    return me_payload(db, user)


@router.get("/invites/{token}")
def invite_info(token: str, request: Request, db: Session = Depends(get_db)):
    ratelimit.hit("invite-info:" + client_ip(request), 60, 3600)
    inv = invite_by_token(db, token)
    if inv is None:
        raise HTTPException(404, "this invite link is invalid, expired, or already used")
    return {"personal": personal.is_personal(db, inv.org_id)}


@router.post("/invites/accept")
def invite_accept(body: TokenIn, request: Request, user: models.User = Depends(current_user),
                  db: Session = Depends(get_db)):
    ratelimit.hit("invite-accept:" + user.id, 20, 3600)
    inv = invite_by_token(db, body.token)
    if inv is None:
        raise HTTPException(400, "this invite link is invalid, expired, or already used")
    accept_invite(db, user, inv)
    audit.log(db, "invite.accepted", user, inv.org_id, client_ip(request))
    db.commit()
    return me_payload(db, user)


@router.get("/sso")
def sso_providers(db: Session = Depends(get_db)):
    return {"providers": sso.configured(school_sso.tenants(db)), "signup": bool(runtime.get("allow_signup")),
            "personal": personal.open_signup(),
            "mail": settings.mail_backend != "none",
            "turnstile_site_key": settings.turnstile_site_key if captcha.required() else "",
            "maintenance": bool(runtime.get("maintenance_mode"))}


def safe_next(value):
    value = value or "/dashboard"
    if not value.startswith("/") or value.startswith("//") or "\\" in value or len(value) > 2000:
        return "/dashboard"
    return value


def login_error(message):
    return RedirectResponse("/login?" + urllib.parse.urlencode({"error": message[:160]}), status_code=302)


@router.get("/sso/{provider}/start")
def sso_start(provider: str, next: str = "/dashboard", db: Session = Depends(get_db)):
    try:
        url, cookie = sso.start(provider, safe_next(next), school_sso.tenants(db))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(scoped_cookie("lm_sso"), cookie, httponly=True, samesite="lax", secure=settings.secure_cookies,
                    max_age=600, path="/api/auth/sso")
    return resp


@router.get("/sso/{provider}/callback")
def sso_callback(provider: str, request: Request, code: str = "", state: str = "",
                 db: Session = Depends(get_db)):
    ratelimit.hit("sso-ip:" + client_ip(request), 60, 600)
    try:
        info = sso.finish(provider, code, state, request.cookies.get(scoped_cookie("lm_sso"), ""), school_sso.tenants(db))
    except Exception as exc:
        return login_error(str(exc) if isinstance(exc, ValueError) else "sign-in failed; try again")
    email = info["email"]
    trusted = bool(info.get("email_verified"))
    district = school_sso.match(db, info)
    auto = district is not None and school_sso.config(district)["auto_setup"]
    ident = db.scalar(select(models.Identity).where(models.Identity.provider == info["provider"],
                                                    models.Identity.subject == info["subject"]))
    user = db.get(models.User, ident.user_id) if ident is not None else None
    if user is None:
        try:
            signed_in = _session_user(request, db)
        except HTTPException:
            signed_in = None
        user = db.scalar(select(models.User).where(models.User.email == email))
        if signed_in is not None:
            if user is not None and user.id != signed_in.id:
                return login_error("that school account's email belongs to a different Live Minutes account")
            user = signed_in
        elif user is not None and not trusted:
            return login_error("an account for " + email + " already exists; sign in with your password first, "
                               "then use this sign-in button again to connect it")
        elif user is not None and (user.email_verified_at is None or user.verified_via not in ("link", "sso")):
            user.password_hash = None
            revoke_sessions(db, user)
            revoke_credentials(db, user)
        if user is None:
            if not trusted and not school_sso.district_domain(db, district, email):
                return login_error("this school account did not share a verified email address; ask your IT office")
            if not (auto or runtime.get("allow_signup") or domain_allowed(db, email) or pending_invite(db, email)):
                return login_error("there is no account for " + email + "; ask your organization for an invite")
            user = models.User(email=email, name=info["name"][:200])
            db.add(user)
            db.flush()
            audit.log(db, "user.signup_sso", user, ip=client_ip(request), provider=provider)
        ident = models.Identity(user_id=user.id, provider=info["provider"], subject=info["subject"], email=email)
        db.add(ident)
    if user.disabled:
        return login_error("this account is disabled")
    ident.last_used_at = time.time()
    same = email.lower() == (user.email or "").lower()
    mark_verified(db, user, "sso", same and (trusted or school_sso.district_domain(db, district, email)), same and trusted)
    if auto:
        school_sso.setup(db, district, user, email, provider)
    if user.totp_enabled_at:
        resp = RedirectResponse("/login?two_factor=1", status_code=302)
        second_step(db, user, resp, request, info.get("next") or "/dashboard")
    else:
        resp = RedirectResponse(info.get("next") or "/dashboard", status_code=302)
        start_session(db, user, resp, request)
    resp.delete_cookie(scoped_cookie("lm_sso"), path="/api/auth/sso", secure=settings.secure_cookies,
                       httponly=True, samesite="lax")
    audit.log(db, "user.login_sso", user, ip=client_ip(request), provider=provider)
    db.commit()
    return resp
