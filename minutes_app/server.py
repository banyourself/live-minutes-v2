import base64
import json
import mimetypes
import os
import re
import secrets
import shutil
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import drafter, llm, motions, template, zoom_oauth
from .config import HOST, LIVE_LINES, LIVE_SECONDS, PORT, ROOT, SESSIONS_DIR, STATIC_DIR, load_env
from .transcript import Transcript

TOKEN_PATH = os.path.join(ROOT, ".capture_token")
UI_HEADER = "X-Minutes-UI"
MAX_BODY = 25 * 1024 * 1024


def capture_token():
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "r", encoding="utf-8") as fh:
            tok = fh.read().strip()
        if tok:
            return tok
    tok = secrets.token_urlsafe(18)
    with open(TOKEN_PATH, "w", encoding="utf-8") as fh:
        fh.write(tok)
    try:
        os.chmod(TOKEN_PATH, 0o600)
    except OSError:
        pass
    return tok


def safe_name(name):
    return re.sub(r"[^\w.\- ]+", "_", os.path.basename(name or "upload"))[:120] or "upload"


class Session:
    def __init__(self, sid):
        self.id = sid
        self.dir = os.path.join(SESSIONS_DIR, sid)
        self.title = "Meeting Minutes"
        self.upload_name = ""
        self.template = ""
        self.mode = ""
        self.run_mode = "live"
        self.provider = ""
        self.model = ""
        self.notes = ""
        self.transcript = Transcript()
        self.draft = {}
        self.problems = []
        self.drafted_upto = 0
        self.drafted_at = 0.0
        self.status = "idle"
        self.error = ""
        self.output = ""
        self.lock = threading.Lock()

    def save(self):
        os.makedirs(self.dir, exist_ok=True)
        data = {k: getattr(self, k) for k in ("id", "title", "upload_name", "template", "mode",
                                              "run_mode", "provider", "model", "notes", "draft",
                                              "problems", "drafted_upto", "output")}
        data["transcript"] = self.transcript.to_list()
        tmp = os.path.join(self.dir, "session.json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, os.path.join(self.dir, "session.json"))

    @classmethod
    def load(cls, sid):
        s = cls(sid)
        with open(os.path.join(s.dir, "session.json"), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for k, v in data.items():
            if k != "transcript":
                setattr(s, k, v)
        s.transcript = Transcript.from_list(data.get("transcript", []))
        return s

    def outline(self):
        if not self.template:
            return None
        cached = getattr(self, "_outline", None)
        if cached is None or cached[0] != self.template:
            self._outline = (self.template, drafter.template_outline(self.template))
        return self._outline[1]

    def summary(self):
        lines = self.transcript.lines
        return {
            "id": self.id, "title": self.title, "upload_name": self.upload_name,
            "mode": self.mode, "run_mode": self.run_mode, "provider": self.provider,
            "model": self.model, "notes": self.notes, "status": self.status, "error": self.error,
            "line_count": len(lines), "pending_lines": len(lines) - self.drafted_upto,
            "transcript_tail": [l.render() for l in lines[-60:]],
            "motions": motions.track(lines),
            "draft": self.draft, "problems": self.problems, "has_output": bool(self.output),
            "outline": self.outline(),
        }


class App:
    def __init__(self):
        self.session = None
        self.oauth_state = ""
        self.token = capture_token()
        self._resume_latest()

    def _resume_latest(self):
        if not os.path.isdir(SESSIONS_DIR):
            return
        ids = sorted(d for d in os.listdir(SESSIONS_DIR)
                     if os.path.exists(os.path.join(SESSIONS_DIR, d, "session.json")))
        if ids:
            try:
                self.session = Session.load(ids[-1])
            except Exception:
                self.session = None

    def need_session(self):
        if self.session is None:
            raise ValueError("start a session first (upload an agenda or template)")
        return self.session


    def run_draft(self, full=False):
        s = self.need_session()
        if not s.provider or not s.model:
            raise ValueError("connect an AI provider and choose a model first")
        if not s.lock.acquire(blocking=False):
            return False
        try:
            s.status, s.error = "drafting", ""
            upto = len(s.transcript.lines)
            if full or not s.draft:
                text, current = s.transcript.text(), (s.draft or None)
            else:
                text, current = s.transcript.text(max(0, s.drafted_upto - 15)), s.draft
            data, bad = drafter.draft(s.provider, s.model, s.template, text, current,
                                      s.notes, generated=(s.mode == "generated"))
            s.draft, s.problems = data, bad
            s.drafted_upto, s.drafted_at = upto, time.time()
            s.status = "idle"
            s.save()
            return True
        except Exception as exc:
            s.status, s.error = "error", str(exc)
            return False
        finally:
            s.lock.release()

    def live_loop(self):
        while True:
            time.sleep(5)
            s = self.session
            if not s or s.run_mode != "live" or not s.provider or not s.model or s.status == "drafting":
                continue
            new = len(s.transcript.lines) - s.drafted_upto
            if new >= LIVE_LINES or (new > 0 and time.time() - s.drafted_at >= LIVE_SECONDS):
                self.run_draft()

    def finish(self):
        s = self.need_session()
        if s.provider and s.model and (not s.draft or len(s.transcript.lines) > s.drafted_upto
                                       or s.run_mode == "after"):
            if not self.run_draft(full=(s.run_mode == "after")) and s.status == "error":
                raise ValueError("drafting failed: " + s.error)
        out = os.path.join(s.dir, safe_name(s.title) + " DRAFT.docx")
        applied, failed = drafter.render(s.template, s.draft or {}, out)
        s.output = out
        s.save()
        return {"applied": applied, "skipped": failed, "file": os.path.basename(out)}


APP = None


class Handler(BaseHTTPRequestHandler):
    server_version = "LiveMinutes/0.1"

    def log_message(self, fmt, *args):
        pass


    def send_json(self, obj, code=200, extra=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def body_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("upload too large")
        raw = self.rfile.read(n) if n else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def host_ok(self):
        host = (self.headers.get("Host") or "").lower()
        port = self.server.server_address[1]
        return host in ("127.0.0.1:%d" % port, "localhost:%d" % port, "[::1]:%d" % port)

    def reject_host(self):
        self.send_response(421)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def capture_cors(self):
        origin = self.headers.get("Origin", "")
        ok = origin.startswith("chrome-extension://") or re.match(r"^https://([\w-]+\.)*zoom\.us$", origin)
        return {"Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Headers": "content-type, x-capture-token",
                "Access-Control-Allow-Methods": "POST",
                "Access-Control-Allow-Private-Network": "true",
                "Vary": "Origin"} if ok else {}

    def send_file(self, path, download_name=None):
        with open(path, "rb") as fh:
            data = fh.read()
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if download_name:
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % download_name)
        self.end_headers()
        self.wfile.write(data)


    def do_OPTIONS(self):
        if not self.host_ok():
            return self.reject_host()
        if self.path.startswith("/api/captions"):
            cors = self.capture_cors()
            if cors:
                self.send_response(204)
                for k, v in cors.items():
                    self.send_header(k, v)
                self.end_headers()
                return
        self.send_response(403)
        self.end_headers()

    def do_GET(self):
        if not self.host_ok():
            return self.reject_host()
        path = urllib.parse.urlparse(self.path)
        try:
            if path.path == "/":
                return self.send_file(os.path.join(STATIC_DIR, "index.html"))
            if path.path.startswith("/static/"):
                name = os.path.basename(path.path)
                full = os.path.join(STATIC_DIR, name)
                if os.path.isfile(full):
                    return self.send_file(full)
                return self.send_json({"error": "not found"}, 404)
            if path.path == "/api/state":
                s = APP.session
                return self.send_json({
                    "session": s.summary() if s else None,
                    "providers": llm.providers(),
                    "zoom": {"configured": zoom_oauth.configured(), "connected": zoom_oauth.connected()},
                    "capture_token": APP.token,
                    "live": {"lines": LIVE_LINES, "seconds": LIVE_SECONDS},
                })
            if path.path == "/api/download":
                s = APP.need_session()
                if not s.output or not os.path.exists(s.output):
                    return self.send_json({"error": "no draft yet; click Finish"}, 400)
                return self.send_file(s.output, os.path.basename(s.output))
            if path.path == "/zoom/connect":
                url, APP.oauth_state = zoom_oauth.authorize_url()
                self.send_response(302)
                self.send_header("Location", url)
                self.end_headers()
                return
            if path.path == "/zoom/callback":
                q = urllib.parse.parse_qs(path.query)
                if q.get("state", [""])[0] != APP.oauth_state or not APP.oauth_state:
                    return self.send_json({"error": "state mismatch; start again from Connect Zoom"}, 400)
                zoom_oauth.exchange_code(q.get("code", [""])[0])
                APP.oauth_state = ""
                self.send_response(302)
                self.send_header("Location", "/")
                self.end_headers()
                return
            return self.send_json({"error": "not found"}, 404)
        except Exception as exc:
            return self.send_json({"error": str(exc)}, 400)

    def do_POST(self):
        if not self.host_ok():
            return self.reject_host()
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/api/captions":
                cors = self.capture_cors()
                if self.headers.get("X-Capture-Token", "") != APP.token:
                    return self.send_json({"error": "bad capture token"}, 403, cors)
                s = APP.need_session()
                body = self.body_json()
                added = 0
                if body.get("snapshot"):
                    added = s.transcript.ingest_snapshot(body["snapshot"][-60000:])
                for ln in body.get("lines") or []:
                    s.transcript.add(ln.get("speaker", ""), ln.get("text", ""), "captions")
                    added += 1
                if added:
                    s.save()
                return self.send_json({"ok": True, "added": added}, 200, cors)

            if self.headers.get(UI_HEADER) != "1":
                return self.send_json({"error": "forbidden"}, 403)
            body = self.body_json()

            if path == "/api/session":
                sid = time.strftime("%Y%m%d-%H%M%S")
                s = Session(sid)
                os.makedirs(s.dir, exist_ok=True)
                name = safe_name(body.get("filename"))
                up = os.path.join(s.dir, name)
                with open(up, "wb") as fh:
                    fh.write(base64.b64decode(body.get("data_b64", "")))
                s.title = (body.get("title") or os.path.splitext(name)[0]).strip()[:120]
                s.upload_name = name
                s.template, s.mode = template.prepare(up, s.dir, s.title, body.get("date", ""))
                s.run_mode = body.get("run_mode", "live")
                if APP.session:
                    s.provider, s.model = APP.session.provider, APP.session.model
                APP.session = s
                s.save()
                return self.send_json({"ok": True, "mode": s.mode})

            if path == "/api/settings":
                s = APP.need_session()
                for k in ("provider", "model", "notes", "run_mode", "title"):
                    if k in body:
                        setattr(s, k, str(body[k])[:4000])
                s.save()
                return self.send_json({"ok": True})

            if path == "/api/import":
                s = APP.need_session()
                kind, n = s.transcript.import_any(body.get("text", ""), body.get("filename", ""))
                s.transcript.sort()
                s.save()
                return self.send_json({"ok": True, "kind": kind, "lines": n})

            if path == "/api/draft":
                threading.Thread(target=APP.run_draft, kwargs={"full": bool(body.get("full"))},
                                 daemon=True).start()
                return self.send_json({"ok": True})

            if path == "/api/finish":
                return self.send_json(APP.finish())

            if path == "/api/session/delete":
                s = APP.need_session()
                shutil.rmtree(s.dir, ignore_errors=True)
                APP.session = None
                return self.send_json({"ok": True})

            if path == "/api/zoom/recordings":
                recs = zoom_oauth.recordings(int(body.get("days", 14)), body.get("meeting_id", ""))
                APP._recs = {r["uuid"]: r for r in recs}
                return self.send_json({"recordings": [{k: v for k, v in r.items() if k != "_raw"} for r in recs]})

            if path == "/api/zoom/import":
                s = APP.need_session()
                rec = getattr(APP, "_recs", {}).get(body.get("uuid", ""))
                if not rec:
                    return self.send_json({"error": "list recordings first"}, 400)
                texts = zoom_oauth.fetch_texts(rec)
                n = s.transcript.import_vtt(texts["vtt"]) if texts["vtt"] else 0
                c = s.transcript.import_chat(texts["chat"]) if texts["chat"] else 0
                s.transcript.sort()
                s.save()
                return self.send_json({"ok": True, "transcript_lines": n, "chat_lines": c})

            if path == "/api/zoom/disconnect":
                zoom_oauth.disconnect()
                return self.send_json({"ok": True})

            return self.send_json({"error": "not found"}, 404)
        except Exception as exc:
            if os.environ.get("MINUTES_DEBUG"):
                traceback.print_exc()
            return self.send_json({"error": str(exc)}, 400)


def main():
    global APP
    load_env()
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    APP = App()
    threading.Thread(target=APP.live_loop, daemon=True).start()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print("Live Minutes is running at http://%s:%d  (Ctrl+C to stop)" % (HOST, PORT))
    print("Capture token for the browser extension: " + APP.token)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
