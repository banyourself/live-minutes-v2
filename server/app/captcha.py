import httpx
from fastapi import HTTPException

from . import runtime
from .settings import settings

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def required():
    return settings.turnstile_enabled and bool(runtime.get("turnstile_required"))


def verify(token, ip="", action=""):
    if not required():
        return
    if not token or len(token) > 2048:
        raise HTTPException(400, "complete the security check first")
    try:
        resp = httpx.post(VERIFY_URL, timeout=8, data={"secret": settings.turnstile_secret, "response": token,
                                                       "remoteip": ip})
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "the security check is unavailable right now; try again in a minute")
    hosts = {host.split(":")[0] for host in settings.hosts()}
    if not data.get("success") or (hosts and (data.get("hostname") not in hosts or data.get("action") != action)):
        raise HTTPException(400, "the security check did not pass; try again")
