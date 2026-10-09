import json
import re

from .settings import settings

UPLOAD_PATHS = (re.compile(r"^/api/orgs/[^/]+/templates$"), re.compile(r"^/api/meetings/[^/]+/import$"),
                re.compile(r"^/api/meetings/[^/]+/references$"),
                re.compile(r"^/api/manage/[^/]+/[^/]+/library$"))
PART_PATH = re.compile(r"^/api/meetings/[^/]+/recording/uploads/[a-f0-9]{32}/\d+$")
PART_LIMIT = 33 * 1024 * 1024
CAPTURE_LIMIT = 2 * 1024 * 1024
DEFAULT_LIMIT = 1024 * 1024
HTML_CSP = ("default-src 'self'; script-src 'self'{challenge}; style-src 'self'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-src {frames}; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'; object-src 'none'")
CHALLENGE = "https://challenges.cloudflare.com"


def html_csp():
    if settings.turnstile_enabled:
        return HTML_CSP.format(challenge=" " + CHALLENGE, frames=CHALLENGE)
    return HTML_CSP.format(challenge="", frames="'none'")
API_CSP = "default-src 'none'; frame-ancestors 'none'"
PERMISSIONS = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"


def limit_for(path):
    if path.startswith("/api/capture/"):
        return CAPTURE_LIMIT
    if PART_PATH.match(path):
        return PART_LIMIT
    if any(p.match(path) for p in UPLOAD_PATHS):
        return settings.max_request_mb * 1024 * 1024
    return DEFAULT_LIMIT


class TooLarge(Exception):
    pass


async def _reply(send, status, detail):
    body = json.dumps({"detail": detail}).encode("utf-8")
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class RequestGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        hosts = settings.hosts()
        if hosts and path != "/api/health" and headers.get("host", "").lower() not in hosts:
            return await _reply(send, 400, "unknown host")
        limit = limit_for(path)
        try:
            if int(headers.get("content-length") or 0) > limit:
                return await _reply(send, 413, "request is too large")
        except ValueError:
            return await _reply(send, 400, "bad content length")
        seen = 0
        started = False

        async def limited_receive():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    raise TooLarge()
            return message

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                extra = [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"same-origin"),
                         (b"x-frame-options", b"DENY"), (b"permissions-policy", PERMISSIONS.encode()),
                         (b"cross-origin-opener-policy", b"same-origin"),
                         (b"cross-origin-resource-policy", b"same-origin"),
                         (b"content-security-policy", (API_CSP if path.startswith("/api/") else html_csp()).encode())]
                if settings.secure_cookies:
                    extra.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                if not settings.turnstile_enabled:
                    extra.append((b"cross-origin-embedder-policy", b"require-corp"))
                if path.startswith("/api/"):
                    extra.append((b"cache-control", b"no-store"))
                names = {k.lower() for k, _ in message.get("headers", [])}
                message = dict(message, headers=list(message.get("headers", [])) + [h for h in extra if h[0] not in names])
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except TooLarge:
            if not started:
                await _reply(send, 413, "request is too large")
