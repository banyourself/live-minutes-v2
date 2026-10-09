import json
import secrets
import time
import urllib.parse

import httpx
import jwt

from .security import decrypt, encrypt
from .settings import settings

_discovery = {}


def tenants(extra=()):
    return sorted(set(settings.microsoft_tenants()) | {t.lower() for t in extra})


def microsoft_ready(extra=()):
    return bool(settings.microsoft_client_id and settings.microsoft_client_secret and tenants(extra))


def configured(extra=()):
    out = []
    if settings.google_client_id and settings.google_client_secret:
        out.append({"id": "google", "label": "Google"})
    if microsoft_ready(extra):
        out.append({"id": "microsoft", "label": "Microsoft"})
    return out


def _conf(provider, extra=()):
    if provider == "google":
        return ("https://accounts.google.com/.well-known/openid-configuration",
                settings.google_client_id, settings.google_client_secret)
    if provider == "microsoft":
        if not tenants(extra):
            raise ValueError("Microsoft sign-in is not set up for any school directory yet")
        return ("https://login.microsoftonline.com/%s/v2.0/.well-known/openid-configuration" % settings.microsoft_tenant,
                settings.microsoft_client_id, settings.microsoft_client_secret)
    raise ValueError("unknown sign-in provider")


def _discover(provider, extra=()):
    url, cid, secret = _conf(provider, extra)
    if not cid or not secret:
        raise ValueError(provider + " sign-in is not configured on this server")
    if url not in _discovery:
        _discovery[url] = httpx.get(url, timeout=20).raise_for_status().json()
    return _discovery[url], cid, secret


def redirect_uri(provider):
    return settings.public_url + "/api/auth/sso/%s/callback" % provider


def start(provider, next_path="/", extra=()):
    meta, cid, _ = _discover(provider, extra)
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    cookie = encrypt(json.dumps({"p": provider, "s": state, "n": nonce, "t": time.time(), "x": next_path}))
    url = meta["authorization_endpoint"] + "?" + urllib.parse.urlencode({
        "client_id": cid, "response_type": "code", "scope": "openid email profile",
        "redirect_uri": redirect_uri(provider), "state": state, "nonce": nonce, "prompt": "select_account"})
    return url, cookie


def finish(provider, code, state, cookie, extra=()):
    try:
        saved = json.loads(decrypt(cookie or ""))
    except (ValueError, json.JSONDecodeError):
        raise ValueError("sign-in expired; try again")
    if (saved.get("p") != provider or not state or not secrets.compare_digest(str(saved.get("s", "")), state)
            or time.time() - saved.get("t", 0) > 600):
        raise ValueError("sign-in expired; try again")
    meta, cid, secret = _discover(provider, extra)
    tok = httpx.post(meta["token_endpoint"], timeout=20, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(provider),
        "client_id": cid, "client_secret": secret}).raise_for_status().json()
    key = jwt.PyJWKClient(meta["jwks_uri"]).get_signing_key_from_jwt(tok["id_token"]).key
    claims = jwt.decode(tok["id_token"], key, algorithms=["RS256"], audience=cid,
                        options={"verify_iss": False})
    iss = claims.get("iss", "")
    if provider == "google" and iss not in ("accounts.google.com", "https://accounts.google.com"):
        raise ValueError("unexpected token issuer")
    if provider == "microsoft" and not (iss.startswith("https://login.microsoftonline.com/") and iss.endswith("/v2.0")):
        raise ValueError("unexpected token issuer")
    if claims.get("nonce") != saved.get("n"):
        raise ValueError("sign-in could not be verified; try again")
    if provider == "google":
        if not claims.get("email_verified"):
            raise ValueError("this Google account's email is not verified")
        email = claims.get("email") or ""
        hd = (claims.get("hd") or "").lower()
        if settings.google_allowed_domains and hd not in settings.google_allowed_domains:
            raise ValueError("use your school Google account to sign in")
        subject = claims.get("sub") or ""
        tid = ""
        verified = True
    else:
        hd = ""
        tid = (claims.get("tid") or "").lower()
        if tid not in tenants(extra) or iss.rstrip("/").split("/")[-2].lower() != tid:
            raise ValueError("this Microsoft account is not from an approved school directory")
        upn = (claims.get("preferred_username") or "").strip().lower()
        mail = (claims.get("email") or "").strip().lower()
        if "@" in upn and "#ext#" not in upn:
            email, verified = upn, True
        elif mail and claims.get("xms_edov") in (True, 1, "1", "true", "True"):
            email, verified = mail, True
        else:
            email, verified = mail or upn, False
        subject = tid + ":" + (claims.get("oid") or "")
        if not claims.get("oid"):
            raise ValueError("the Microsoft account did not include an object ID")
    email = email.strip().lower()
    if "@" not in email or not subject:
        raise ValueError("the account did not share an email address")
    return {"provider": provider, "subject": subject, "email": email, "name": claims.get("name") or "",
            "next": saved.get("x") or "/", "tid": tid, "hd": hd, "email_verified": verified}
