import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import ai_runtime, db, free_ai, jobs, seo
from .middleware import RequestGuard
from .routes import (admin, ai, assistant, auth, backups, capture, console, directory, downloads, governance, history, library,
                     mcp, meetings, notifications, officers, openrouter, orgs, provisioning, recordings,
                     oauth, public, records, references, reports, samples, scheduling, share, templates, zoom)
from .settings import settings


class FingerprintedFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "x-live-minutes"
CSRF_EXEMPT = ("/api/capture/", "/api/zoom/events")


def create_app(start_worker=None):
    settings.validate()
    db.init_db()
    ai_runtime.ensure_free_conn()
    docs = settings.enable_api_docs
    app = FastAPI(title="Live Minutes", version="1.0.0", docs_url="/api/docs" if docs else None,
                  redoc_url=None, openapi_url="/api/openapi.json" if docs else None)

    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                           allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
                           allow_headers=["Content-Type", "X-Live-Minutes"])

    @app.middleware("http")
    async def csrf(request: Request, call_next):
        path = request.url.path
        if (request.method not in SAFE_METHODS and path.startswith("/api/")
                and not path.startswith(CSRF_EXEMPT) and request.headers.get(CSRF_HEADER) != "1"):
            return JSONResponse({"detail": "missing X-Live-Minutes header"}, status_code=403)
        return await call_next(request)

    app.add_middleware(RequestGuard)

    @app.middleware("http")
    async def free_run_header(request: Request, call_next):
        token = free_ai.current_run.set((request.headers.get("x-free-ai-run") or "")[:32])
        try:
            return await call_next(request)
        finally:
            free_ai.current_run.reset(token)

    @app.exception_handler(free_ai.Pending)
    async def free_ai_pending(_request, exc):
        return JSONResponse({"pending": exc.payload}, status_code=202)

    @app.exception_handler(ValueError)
    async def value_error(_request, exc):
        return JSONResponse({"detail": " ".join(str(exc).split())[:300]}, status_code=400)

    for r in (auth, orgs, officers, directory, admin, console, ai, templates, meetings, scheduling, records, share,
              notifications, library, provisioning, governance, reports, backups, recordings, mcp, oauth,
              openrouter, assistant, history, samples, capture, zoom, references, downloads, public):
        app.include_router(r.router)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/ready")
    def ready():
        try:
            with db.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse({"ok": False}, status_code=503)
        return {"ok": True}

    dist = os.path.realpath(settings.web_dist)
    if os.path.isdir(os.path.join(dist, "assets")):
        app.mount("/assets", FingerprintedFiles(directory=os.path.join(dist, "assets")), name="assets")

    @app.get("/robots.txt", include_in_schema=False)
    def robots():
        return PlainTextResponse(seo.robots_txt(), headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/.well-known/security.txt", include_in_schema=False)
    def security_txt():
        return PlainTextResponse(seo.security_txt(), headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/security.txt", include_in_schema=False)
    def security_txt_legacy():
        return RedirectResponse("/.well-known/security.txt", status_code=301)

    @app.get("/sitemap.xml", include_in_schema=False)
    def sitemap():
        with db.SessionLocal() as session:
            body = seo.sitemap_xml(session)
        return Response(body, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "not found")
        candidate = os.path.realpath(os.path.join(dist, path))
        if path and os.path.commonpath([candidate, dist]) == dist and os.path.isfile(candidate):
            return FileResponse(candidate)
        index = os.path.join(dist, "index.html")
        if os.path.isfile(index):
            with db.SessionLocal() as session:
                page, meta = seo.render(index, "/" + path, session)
            headers = {"Cache-Control": "no-cache, no-transform"}
            if not meta["index"]:
                headers["X-Robots-Tag"] = seo.NOINDEX
            return HTMLResponse(page, status_code=meta["status"], headers=headers)
        return JSONResponse({"detail": "web app not built; run npm run build in web/"}, status_code=404)

    if settings.inline_worker if start_worker is None else start_worker:
        app.state.worker_stop = jobs.start_inline()

    return app
