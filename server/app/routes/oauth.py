import base64
import hashlib
import json
import re
import secrets
import time
import urllib.parse

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import audit, models, notify, ratelimit
from ..db import get_db
from ..deps import client_ip, current_user
from ..security import decrypt, encrypt, new_token, token_hash
from ..settings import settings

router = APIRouter(tags=["oauth"])
ACCESS_SECONDS = 3600
REFRESH_DAYS = 90
CODE_SECONDS = 600
REQUEST_SECONDS = 900
MAX_CLIENTS = 5000
MAX_GRANTS = 20
SCOPES = ("minutes.read", "minutes.write")
VERIFIER = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")
KNOWN = {"claude.ai": "Claude", "chatgpt.com": "ChatGPT", "chat.openai.com": "ChatGPT", "gemini.google.com": "Gemini",
         "grok.com": "Grok", "chat.mistral.ai": "Le Chat", "perplexity.ai": "Perplexity", "www.perplexity.ai": "Perplexity"}
NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def base():
    return settings.public_url.rstrip("/")


def resource_url():
    return base() + "/mcp"


def resource_metadata_url():
    return base() + "/.well-known/oauth-protected-resource"


def protected_resource():
    return {"resource": resource_url(), "authorization_servers": [base()], "bearer_methods_supported": ["header"],
            "scopes_supported": list(SCOPES), "resource_name": "Live Minutes"}


@router.get("/.well-known/oauth-protected-resource", include_in_schema=False)
@router.get("/.well-known/oauth-protected-resource/mcp", include_in_schema=False)
def resource_document():
    return JSONResponse(protected_resource())


@router.get("/.well-known/oauth-authorization-server", include_in_schema=False)
@router.get("/.well-known/oauth-authorization-server/mcp", include_in_schema=False)
def server_document():
    return JSONResponse({"issuer": base(), "authorization_endpoint": base() + "/oauth/authorize",
                         "token_endpoint": base() + "/oauth/token", "registration_endpoint": base() + "/oauth/register",
                         "revocation_endpoint": base() + "/oauth/revoke", "response_types_supported": ["code"],
                         "grant_types_supported": ["authorization_code", "refresh_token"],
                         "code_challenge_methods_supported": ["S256"],
                         "token_endpoint_auth_methods_supported": ["none"], "scopes_supported": list(SCOPES),
                         "service_documentation": base() + "/account"})


def oauth_error(code, description, status=400):
    return JSONResponse({"error": code, "error_description": description}, status_code=status, headers=NO_STORE)


def redirect_ok(uri):
    if not isinstance(uri, str) or len(uri) > 500 or "#" in uri:
        return False
    parts = urllib.parse.urlsplit(uri)
    host = (parts.hostname or "").lower()
    if parts.scheme == "https" and host and not parts.username and not parts.password:
        return True
    return parts.scheme == "http" and host in ("localhost", "127.0.0.1", "::1")


def host_of(uri):
    return (urllib.parse.urlsplit(uri).hostname or "").lower()


@router.post("/oauth/register", include_in_schema=False)
async def register(request: Request, db: Session = Depends(get_db)):
    ratelimit.hit("oauth-register:" + client_ip(request), 30, 3600, "too many apps registered from your network")
    try:
        body = json.loads(await request.body() or b"{}")
    except json.JSONDecodeError:
        return oauth_error("invalid_client_metadata", "send JSON")
    if not isinstance(body, dict):
        return oauth_error("invalid_client_metadata", "send a JSON object")
    uris = body.get("redirect_uris")
    if not isinstance(uris, list) or not 1 <= len(uris) <= 5 or not all(redirect_ok(u) for u in uris):
        return oauth_error("invalid_redirect_uri", "use 1 to 5 https redirect addresses (or http on localhost)")
    grants = body.get("grant_types") or ["authorization_code"]
    if not isinstance(grants, list) or not set(grants) <= {"authorization_code", "refresh_token"}:
        return oauth_error("invalid_client_metadata", "only authorization_code and refresh_token are supported")
    if db.scalar(select(func.count()).select_from(models.OAuthClient)) >= MAX_CLIENTS:
        return oauth_error("temporarily_unavailable", "this server has too many registered apps", 503)
    name = " ".join(str(body.get("client_name") or "").split())[:120] or KNOWN.get(host_of(uris[0]), "AI app")
    c = models.OAuthClient(id="lmc_" + secrets.token_urlsafe(24), name=name, redirect_uris=list(dict.fromkeys(uris)))
    db.add(c)
    db.commit()
    return JSONResponse({"client_id": c.id, "client_id_issued_at": int(c.created_at), "client_name": c.name,
                         "redirect_uris": c.redirect_uris, "grant_types": ["authorization_code", "refresh_token"],
                         "response_types": ["code"], "token_endpoint_auth_method": "none"},
                        status_code=201, headers=NO_STORE)


def resource_ok(value):
    return not value or value.rstrip("/") in (resource_url(), base())


@router.get("/oauth/authorize", include_in_schema=False)
def authorize(request: Request, db: Session = Depends(get_db)):
    q = request.query_params
    client = db.get(models.OAuthClient, q.get("client_id", ""))
    uri = q.get("redirect_uri", "")
    if client is None:
        return PlainTextResponse("This app is not registered with Live Minutes. Remove the connector and add it again.", 400)
    if not uri and len(client.redirect_uris) == 1:
        uri = client.redirect_uris[0]
    if uri not in client.redirect_uris:
        return PlainTextResponse("The app sent a return address it did not register.", 400)

    def back(error, description):
        query = {"error": error, "error_description": description}
        if q.get("state"):
            query["state"] = q["state"]
        return RedirectResponse(uri + ("&" if "?" in uri else "?") + urllib.parse.urlencode(query), status_code=302)

    if q.get("response_type") != "code":
        return back("unsupported_response_type", "only the code flow is supported")
    challenge = q.get("code_challenge", "")
    if q.get("code_challenge_method") != "S256" or not 43 <= len(challenge) <= 128:
        return back("invalid_request", "PKCE with S256 is required")
    if not resource_ok(q.get("resource", "")):
        return back("invalid_target", "this server only issues tokens for " + resource_url())
    scopes = set((q.get("scope") or "").split()) or set(SCOPES)
    blob = encrypt(json.dumps({"c": client.id, "u": uri, "ch": challenge, "s": q.get("state", "")[:500],
                               "w": "minutes.write" in scopes or not (scopes & set(SCOPES)), "exp": time.time() + REQUEST_SECONDS}))
    return RedirectResponse("/connect?" + urllib.parse.urlencode({"r": blob}), status_code=302)


def pending(db, blob):
    try:
        data = json.loads(decrypt(blob))
    except (ValueError, TypeError):
        raise HTTPException(400, "this connection request is not valid; start again from the app")
    if data.get("exp", 0) < time.time():
        raise HTTPException(400, "this connection request expired; start again from the app")
    client = db.get(models.OAuthClient, data.get("c", ""))
    if client is None or data.get("u") not in client.redirect_uris:
        raise HTTPException(400, "this app is no longer registered; start again from the app")
    return data, client


def with_query(uri, params):
    return uri + ("&" if "?" in uri else "?") + urllib.parse.urlencode({k: v for k, v in params.items() if v})


@router.get("/api/oauth/request")
def describe(r: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    data, client = pending(db, r)
    host = host_of(data["u"])
    return {"client_name": client.name, "return_host": host, "known": KNOWN.get(host, ""), "wants_write": data["w"],
            "user": user.name or user.email}


class Decision(BaseModel):
    r: str
    allow: bool
    can_write: bool = False


@router.post("/api/oauth/decide")
def decide(body: Decision, request: Request, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    data, client = pending(db, body.r)
    if not body.allow:
        return {"redirect": with_query(data["u"], {"error": "access_denied", "state": data["s"]})}
    raw = new_token()
    db.add(models.OAuthCode(code_hash=token_hash("code:" + raw), client_id=client.id, user_id=user.id,
                            redirect_uri=data["u"], challenge=data["ch"], can_write=bool(body.can_write),
                            expires_at=time.time() + CODE_SECONDS))
    audit.log(db, "oauth.approved", user, ip=client_ip(request), app=client.name, return_host=host_of(data["u"]),
              can_write=bool(body.can_write))
    db.commit()
    return {"redirect": with_query(data["u"], {"code": raw, "state": data["s"]})}


def connected(db, user_id, name, can_write):
    user = db.get(models.User, user_id)
    what = "read your meetings and save drafts for you to review" if can_write else "read your meetings"
    notify.send(db, [user], "app_connected", None, "%s is connected to your Live Minutes account" % name,
                "%s can now %s. It can only see what you can see, and it cannot approve minutes. You can see and "
                "disconnect your apps under My account, AI. If you did not connect %s, disconnect it there and change "
                "your password." % (name, what, name), "/account?tab=ai")


def issue(db, user_id, client, can_write, grant=None):
    access, refresh = "lma_" + new_token(), "lmr_" + new_token()
    now = time.time()
    if grant is None:
        db.execute(delete(models.PersonalToken).where(models.PersonalToken.user_id == user_id,
                                                      models.PersonalToken.client_id == client.id))
        grants = db.scalars(select(models.PersonalToken).where(models.PersonalToken.user_id == user_id,
                                                               models.PersonalToken.client_id.is_not(None))
                            .order_by(models.PersonalToken.created_at)).all()
        for old in grants[:max(0, len(grants) - MAX_GRANTS + 1)]:
            db.delete(old)
        grant = models.PersonalToken(user_id=user_id, name=client.name + " (connected app)", can_write=can_write,
                                     client_id=client.id, token_hash="", expires_at=now)
        db.add(grant)
        connected(db, user_id, client.name, can_write)
    grant.token_hash = token_hash("pat:" + access)
    grant.refresh_prev_hash = grant.refresh_hash
    grant.refresh_hash = token_hash("refresh:" + refresh)
    grant.expires_at = now + ACCESS_SECONDS
    grant.refresh_expires_at = now + REFRESH_DAYS * 86400
    client.last_used_at = now
    db.commit()
    return JSONResponse({"access_token": access, "token_type": "Bearer", "expires_in": ACCESS_SECONDS,
                         "refresh_token": refresh, "scope": " ".join(SCOPES if grant.can_write else SCOPES[:1])},
                        headers=NO_STORE)


def challenge_for(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


@router.post("/oauth/token", include_in_schema=False)
def token(request: Request, grant_type: str = Form(""), code: str = Form(""), redirect_uri: str = Form(""),
          client_id: str = Form(""), code_verifier: str = Form(""), refresh_token: str = Form(""),
          resource: str = Form(""), db: Session = Depends(get_db)):
    ratelimit.hit("oauth-token:" + client_ip(request), 3000, 600, "too many token requests")
    ratelimit.hit("oauth-client:" + client_id[:80], 60, 600, "too many token requests for this app")
    client = db.get(models.OAuthClient, client_id)
    if client is None:
        return oauth_error("invalid_client", "unknown client_id", 401)
    if not resource_ok(resource):
        return oauth_error("invalid_target", "this server only issues tokens for " + resource_url())
    if grant_type == "authorization_code":
        row = db.scalar(select(models.OAuthCode).where(models.OAuthCode.code_hash == token_hash("code:" + code)))
        if row is None or row.client_id != client.id or row.used_at is not None or row.expires_at < time.time():
            if row is not None and row.used_at is not None:
                db.execute(delete(models.PersonalToken).where(models.PersonalToken.user_id == row.user_id,
                                                              models.PersonalToken.client_id == client.id))
                db.commit()
            return oauth_error("invalid_grant", "the code is not valid or has expired")
        if redirect_uri and redirect_uri != row.redirect_uri:
            return oauth_error("invalid_grant", "redirect_uri does not match")
        if not VERIFIER.match(code_verifier) or not secrets.compare_digest(challenge_for(code_verifier), row.challenge):
            return oauth_error("invalid_grant", "code_verifier does not match")
        row.used_at = time.time()
        user = db.get(models.User, row.user_id)
        if user is None or user.disabled:
            db.commit()
            return oauth_error("invalid_grant", "this account cannot connect apps")
        return issue(db, user.id, client, row.can_write)
    if grant_type == "refresh_token":
        presented = token_hash("refresh:" + refresh_token)
        grant = db.scalar(select(models.PersonalToken).where(models.PersonalToken.refresh_hash == presented))
        if grant is None:
            stolen = db.scalar(select(models.PersonalToken).where(models.PersonalToken.refresh_prev_hash == presented))
            if stolen is not None:
                audit.log(db, "oauth.refresh_reused", None, client=stolen.client_id, user_id=stolen.user_id)
                db.delete(stolen)
                db.commit()
        if grant is None or grant.client_id != client.id or (grant.refresh_expires_at or 0) < time.time():
            return oauth_error("invalid_grant", "the refresh token is not valid; connect the app again")
        user = db.get(models.User, grant.user_id)
        if user is None or user.disabled:
            return oauth_error("invalid_grant", "this account cannot connect apps")
        return issue(db, user.id, client, grant.can_write, grant)
    return oauth_error("unsupported_grant_type", "use authorization_code or refresh_token")


@router.post("/oauth/revoke", include_in_schema=False)
def revoke(request: Request, token: str = Form(""), client_id: str = Form(""), db: Session = Depends(get_db)):
    ratelimit.hit("oauth-token:" + client_ip(request), 3000, 600, "too many token requests")
    grant = db.scalar(select(models.PersonalToken).where(
        (models.PersonalToken.refresh_hash == token_hash("refresh:" + token)) |
        (models.PersonalToken.token_hash == token_hash("pat:" + token))))
    if grant is not None and grant.client_id and grant.client_id == client_id:
        db.delete(grant)
        db.commit()
    return JSONResponse({}, headers=NO_STORE)

