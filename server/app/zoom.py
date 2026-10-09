import base64
import hashlib
import hmac
import json
import time
import urllib.parse
from datetime import date, timedelta

import httpx

from .security import decrypt, encrypt
from .settings import settings

API = "https://api.zoom.us/v2"
CAPTION_SHARE = 0.6
MAX_PAGES = 20
SIGNATURE_AGE = 300


def configured():
    return bool(settings.zoom_client_id and settings.zoom_client_secret)


def redirect_uri():
    return settings.public_url + "/api/zoom/callback"


def _basic():
    raw = settings.zoom_client_id + ":" + settings.zoom_client_secret
    return "Basic " + base64.b64encode(raw.encode()).decode()


def authorize_url(state):
    return "https://zoom.us/oauth/authorize?" + urllib.parse.urlencode(
        {"response_type": "code", "client_id": settings.zoom_client_id, "redirect_uri": redirect_uri(),
         "state": state})


def _token(params):
    r = httpx.post("https://zoom.us/oauth/token", params=params, timeout=30,
                   headers={"Authorization": _basic(), "Content-Type": "application/x-www-form-urlencoded"})
    if r.status_code != 200:
        raise ValueError("Zoom token error %s: %s" % (r.status_code, r.text[:300]))
    tok = r.json()
    tok["expires_at"] = time.time() + int(tok.get("expires_in", 3600))
    return tok


def exchange(code):
    return _token({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri()})


def identity(access_token):
    r = httpx.get(API + "/users/me", headers={"Authorization": "Bearer " + access_token}, timeout=30)
    if r.status_code != 200:
        raise ValueError("Zoom returned %s: %s" % (r.status_code, r.text[:300]))
    me = r.json()
    if not me.get("id"):
        raise ValueError("Zoom did not say which account signed in")
    return {"id": str(me.get("id", ""))[:64], "account_id": str(me.get("account_id", ""))[:64],
            "email": str(me.get("email", ""))[:320]}


def revoke_token(token):
    if not token:
        return False
    try:
        r = httpx.post("https://zoom.us/oauth/revoke", params={"token": token}, headers={"Authorization": _basic()},
                       timeout=20)
    except httpx.HTTPError:
        return False
    return r.status_code == 200


def sign(message):
    return hmac.new(settings.zoom_secret_token.encode(), message, hashlib.sha256).hexdigest()


def signature_ok(timestamp, body, signature, clock=time.time):
    if not settings.zoom_secret_token or not timestamp.isdigit() or abs(clock() - int(timestamp)) > SIGNATURE_AGE:
        return False
    return hmac.compare_digest("v0=" + sign(b"v0:" + timestamp.encode() + b":" + body), signature or "")


class Client:
    def __init__(self, conn, db):
        self.conn, self.db = conn, db
        self.tok = json.loads(decrypt(conn.token_enc))

    def _stale(self):
        return self.tok.get("expires_at", 0) < time.time() + 120

    def _access(self):
        if self._stale():
            self.db.refresh(self.conn, with_for_update=True)
            self.tok = json.loads(decrypt(self.conn.token_enc))
            if self._stale():
                self.tok = _token({"grant_type": "refresh_token", "refresh_token": self.tok["refresh_token"]})
                self.conn.token_enc = encrypt(json.dumps(self.tok))
            self.db.commit()
        return self.tok["access_token"]

    def get(self, url, raw=False):
        r = httpx.get(url, headers={"Authorization": "Bearer " + self._access()}, timeout=120, follow_redirects=True)
        if r.status_code != 200:
            raise ValueError("Zoom returned %s: %s" % (r.status_code, r.text[:300]))
        return r.content if raw else r.json()

    def me(self):
        return self.get(API + "/users/me")

    def settings(self):
        return self.get(API + "/users/me/settings")

    def _window(self, start, end):
        out, page = [], ""
        for _ in range(MAX_PAGES):
            query = {"from": start.isoformat(), "to": end.isoformat(), "page_size": 300}
            if page:
                query["next_page_token"] = page
            data = self.get(API + "/users/me/recordings?" + urllib.parse.urlencode(query))
            out += data.get("meetings", [])
            page = data.get("next_page_token") or ""
            if not page:
                break
        return out

    def recordings(self, days=30):
        end = date.today()
        return self._window(end - timedelta(days=min(days, 30)), end)

    def recordings_since(self, days=180):
        out, end = [], date.today()
        while days > 0:
            span = min(days, 30)
            start = end - timedelta(days=span)
            out += self._window(start, end)
            end, days = start, days - span
        return out

    def find_share(self, share_url, days=180):
        want = share_key(share_url)
        return next((m for m in self.recordings_since(days) if share_key(m.get("share_url", "")) == want), None)

    def download(self, url, path, limit):
        size = 0
        with httpx.stream("GET", url, headers={"Authorization": "Bearer " + self._access()}, timeout=600,
                          follow_redirects=True) as r:
            if r.status_code != 200:
                raise ValueError("Zoom returned %s while downloading the recording" % r.status_code)
            with open(path, "wb") as fh:
                for chunk in r.iter_bytes(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise ValueError("the recording is larger than this server allows")
                    fh.write(chunk)
        return size

    def _file(self, meeting, kind):
        f = next((x for x in meeting.get("recording_files", []) if x.get("file_type") == kind and x.get("download_url")), None)
        return self.get(f["download_url"], raw=True).decode("utf-8", "replace") if f else ""

    def texts(self, meeting):
        captions, transcript = self._file(meeting, "CC"), self._file(meeting, "TRANSCRIPT")
        use_captions = bool(captions) and len(captions) >= CAPTION_SHARE * len(transcript)
        return {"vtt": captions if use_captions else transcript, "chat": self._file(meeting, "CHAT"),
                "source": "captions" if use_captions else ("transcript" if transcript else "")}

    def revoke(self):
        try:
            token = self._access()
        except (ValueError, KeyError, httpx.HTTPError):
            token = self.tok.get("access_token", "")
        return revoke_token(token)


def share_key(url):
    parts = urllib.parse.urlsplit((url or "").strip())
    host = (parts.hostname or "").lower()
    if not (host == "zoom.us" or host.endswith(".zoom.us")) or "/rec/" not in parts.path:
        return ""
    return parts.path.rstrip("/").rsplit("/", 1)[-1].split(".")[0]


SETTINGS_URL = "https://zoom.us/profile/setting?tab=recording"
MEETING_SETTINGS_URL = "https://zoom.us/profile/setting?tab=meeting"
CHECKS = [
    ("cloud_recording", "Cloud recording", "Recordings are saved to Zoom's cloud so Live Minutes can import them.", True,
     "Recording tab, Cloud recording", SETTINGS_URL),
    ("audio_transcript", "Create audio transcript", "Zoom writes the transcript the AI drafts the minutes from.", True,
     "Recording tab, Cloud recording, Advanced cloud recording settings, Create audio transcript", SETTINGS_URL),
    ("save_chat", "Save chat messages", "The meeting chat is imported with the recording.", True,
     "Recording tab, Cloud recording, Save chat messages from the meeting", SETTINGS_URL),
    ("save_captions", "Save closed captions", "Zoom keeps the meeting's live captions with the recording. Live Minutes uses "
     "them instead of the audio transcript when they cover the meeting, because they are often more accurate.", False,
     "Recording tab, Cloud recording, Advanced cloud recording settings, Save closed captions as a VTT file", SETTINGS_URL),
    ("auto_recording", "Automatic recording in the cloud", "Every meeting records itself, so nobody has to remember.", False,
     "Recording tab, Automatic recording, Record in the cloud", SETTINGS_URL),
    ("captions", "Automated captions", "Captions let the desktop app or Chrome extension draft minutes during the meeting.", False,
     "Meeting tab, Automated captions", MEETING_SETTINGS_URL),
]


def _flag(value):
    if isinstance(value, dict):
        return bool(value.get("enable", value.get("enabled", False)))
    return bool(value)


def read_checks(raw):
    rec = raw.get("recording") or {}
    meet = raw.get("in_meeting") or {}
    caption = meet.get("auto_generated_captions", meet.get("closed_captioning", meet.get("closed_caption")))
    if isinstance(caption, dict):
        caption = caption.get("enable") and caption.get("auto_transcribing", caption.get("enable"))
    return {"cloud_recording": _flag(rec.get("cloud_recording")),
            "audio_transcript": _flag(rec.get("recording_audio_transcript", rec.get("audio_transcript"))),
            "save_chat": _flag(rec.get("save_chat_text")),
            "save_captions": _flag(rec.get("save_closed_caption", rec.get("save_caption"))),
            "auto_recording": rec.get("auto_recording") == "cloud",
            "captions": _flag(caption)}

