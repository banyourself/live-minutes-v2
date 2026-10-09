import base64
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from .config import ROOT, env, PORT

TOKEN_FILE = os.path.join(ROOT, ".zoom_user_token.json")
API = "https://api.zoom.us/v2"


class ZoomNotConfigured(Exception):
    pass


def configured():
    return bool(env("ZOOM_APP_CLIENT_ID") and env("ZOOM_APP_CLIENT_SECRET"))


def redirect_uri():
    return env("ZOOM_APP_REDIRECT_URI", "http://localhost:%d/zoom/callback" % PORT)


def _basic():
    raw = env("ZOOM_APP_CLIENT_ID") + ":" + env("ZOOM_APP_CLIENT_SECRET")
    return "Basic " + base64.b64encode(raw.encode()).decode()


def authorize_url():
    if not configured():
        raise ZoomNotConfigured("the Zoom app is not configured (see docs/ZOOM-APP-SETUP.md)")
    state = secrets.token_urlsafe(16)
    url = "https://zoom.us/oauth/authorize?" + urllib.parse.urlencode(
        {"response_type": "code", "client_id": env("ZOOM_APP_CLIENT_ID"),
         "redirect_uri": redirect_uri(), "state": state})
    return url, state


def _token_request(params):
    req = urllib.request.Request("https://zoom.us/oauth/token?" + urllib.parse.urlencode(params),
                                 data=b"", method="POST")
    req.add_header("Authorization", _basic())
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            tok = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError("Zoom token error %s: %s" % (exc.code, exc.read().decode("utf-8", "replace")[:300]))
    tok["expires_at"] = time.time() + int(tok.get("expires_in", 3600))
    with open(TOKEN_FILE, "w", encoding="utf-8") as fh:
        json.dump(tok, fh)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass
    return tok


def exchange_code(code):
    return _token_request({"grant_type": "authorization_code", "code": code,
                           "redirect_uri": redirect_uri()})


def connected():
    return os.path.exists(TOKEN_FILE)


def access_token():
    if not connected():
        raise ZoomNotConfigured("Zoom is not connected. The host account must click Connect Zoom first.")
    with open(TOKEN_FILE, "r", encoding="utf-8") as fh:
        tok = json.load(fh)
    if tok.get("expires_at", 0) < time.time() + 120:
        tok = _token_request({"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
    return tok["access_token"]


def disconnect():
    if connected():
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as fh:
                tok = json.load(fh)
            req = urllib.request.Request("https://zoom.us/oauth/revoke?" + urllib.parse.urlencode(
                {"token": tok.get("access_token", "")}), data=b"", method="POST")
            req.add_header("Authorization", _basic())
            urllib.request.urlopen(req, timeout=30).close()
        except Exception:
            pass
        os.remove(TOKEN_FILE)


def _get(url, raw=False):
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + access_token())
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = resp.read()
    return body if raw else json.loads(body.decode("utf-8"))


def recordings(days=14, meeting_id=""):
    end = date.today()
    start = end - timedelta(days=days)
    data = _get(API + "/users/me/recordings?" + urllib.parse.urlencode(
        {"from": start.isoformat(), "to": end.isoformat(), "page_size": 100}))
    meetings = data.get("meetings", [])
    if meeting_id:
        digits = "".join(c for c in meeting_id if c.isdigit())
        meetings = [m for m in meetings if str(m.get("id", "")) == digits]
    return [{"uuid": m.get("uuid"), "id": m.get("id"), "topic": m.get("topic"),
             "start_time": m.get("start_time"),
             "files": [f.get("file_type") for f in m.get("recording_files", [])],
             "_raw": m} for m in meetings]


def fetch_texts(meeting):
    out = {"vtt": "", "chat": ""}
    for f in meeting["_raw"].get("recording_files", []):
        kind = f.get("file_type")
        if kind in ("TRANSCRIPT", "CHAT") and f.get("download_url"):
            text = _get(f["download_url"], raw=True).decode("utf-8", "replace")
            out["vtt" if kind == "TRANSCRIPT" else "chat"] = text
    return out
