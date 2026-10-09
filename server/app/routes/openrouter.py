import base64
import hashlib
import json
import secrets
import time
import urllib.parse

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from minutes_app import llm

from .. import audit, models
from ..db import get_db
from ..deps import client_ip, current_user, scoped_cookie
from ..security import decrypt, encrypt
from ..settings import settings
from .ai import OWNER_SCOPES, audit_org, need_manage

router = APIRouter(tags=["ai"])
COOKIE = "lm_openrouter"
AUTH = "https://openrouter.ai/auth"
EXCHANGE = "https://openrouter.ai/api/v1/auth/keys"


def back(scope_name, error="", ok=False):
    path = "/account" if scope_name == "user" else "/settings" if scope_name == "org" else "/manage"
    q = {"openrouter": "connected"} if ok else {"openrouter_error": error[:160]}
    return RedirectResponse(path + "?" + urllib.parse.urlencode(q), status_code=302)


@router.get("/api/ai/openrouter/start")
def start(scope: str, scope_id: str = "", user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    scope_id = user.id if scope == "user" else scope_id
    if scope not in OWNER_SCOPES:
        return back(scope, "choose who owns this AI")
    need_manage(db, user, scope, scope_id)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = encrypt(json.dumps({"v": verifier, "s": scope, "i": scope_id, "u": user.id, "t": time.time()}))
    url = AUTH + "?" + urllib.parse.urlencode({"callback_url": settings.public_url + "/api/ai/openrouter/callback",
                                               "code_challenge": challenge, "code_challenge_method": "S256"})
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(scoped_cookie(COOKIE), state, httponly=True, samesite="lax", secure=settings.secure_cookies,
                    max_age=600, path="/api/ai/openrouter")
    return resp


@router.get("/api/ai/openrouter/callback")
def callback(request: Request, code: str = "", user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        saved = json.loads(decrypt(request.cookies.get(scoped_cookie(COOKIE), "")))
    except (ValueError, json.JSONDecodeError):
        return back("user", "the OpenRouter sign-in expired; try again")
    scope_name, scope_id = saved["s"], saved["i"]
    if saved.get("u") != user.id or time.time() - saved.get("t", 0) > 600 or not code:
        return back(scope_name, "the OpenRouter sign-in expired; try again")
    need_manage(db, user, scope_name, scope_id)
    try:
        r = httpx.post(EXCHANGE, json={"code": code, "code_verifier": saved["v"], "code_challenge_method": "S256"},
                       timeout=20, follow_redirects=False)
        key = r.json().get("key", "") if r.status_code == 200 else ""
    except (httpx.HTTPError, ValueError):
        key = ""
    if not key:
        return back(scope_name, "OpenRouter did not return a key; try again")
    base = llm.OPENAI_COMPATIBLE["openrouter"][1]
    c = models.AIConnection(org_id=scope_id if scope_name == "org" else None, owner_scope=scope_name, owner_id=scope_id,
                            label="OpenRouter (connected account)", provider="openrouter", model="openrouter/auto",
                            base_url=base, api_key_enc=encrypt(key), created_by=user.id)
    db.add(c)
    audit.log(db, "ai.connected_openrouter", user, audit_org(c), client_ip(request), owner=scope_name, owner_id=scope_id)
    db.commit()
    resp = back(scope_name, ok=True)
    resp.delete_cookie(scoped_cookie(COOKIE), path="/api/ai/openrouter", secure=settings.secure_cookies, httponly=True,
                       samesite="lax")
    return resp
