import json
import os
import re
import secrets
import shutil
import time
import zipfile

from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from . import storage
from .settings import settings

CHUNK = 32 * 1024 * 1024
UPLOAD_ID = re.compile(r"^[a-f0-9]{32}$")
EXT = {"video/mp4": "mp4", "audio/mp4": "m4a", "video/quicktime": "mov", "video/webm": "webm", "audio/mpeg": "mp3",
       "audio/wav": "wav", "audio/ogg": "ogg"}


def max_bytes():
    return int(os.environ.get("MAX_RECORDING_MB", "4096")) * 1024 * 1024


def sniff(head):
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand.startswith(b"M4A") or brand.startswith(b"M4B"):
            return "audio/mp4"
        if brand == b"qt  ":
            return "video/quicktime"
        return "video/mp4"
    if head[:4] == b"\x1aE\xdf\xa3":
        return "video/webm"
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return "audio/mpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav"
    if head[:4] == b"OggS":
        return "audio/ogg"
    return None


def sniff_file(path):
    with open(path, "rb") as fh:
        return sniff(fh.read(64))


def staging(upload_id=""):
    root = os.path.join(settings.storage_dir, ".uploads")
    if upload_id:
        if not UPLOAD_ID.match(upload_id):
            raise HTTPException(404, "upload not found")
        return os.path.join(root, upload_id)
    return root


def open_uploads(user_id, org_id=""):
    root = staging()
    mine = total = in_org = reserved = 0
    for entry in os.listdir(root) if os.path.isdir(root) else []:
        total += 1
        try:
            with open(os.path.join(root, entry, "meta.json"), encoding="utf-8") as fh:
                m = json.load(fh)
        except (OSError, ValueError):
            continue
        mine += m.get("user") == user_id
        in_org += bool(org_id) and m.get("org") == org_id
        reserved += int(m.get("size") or 0)
    return mine, total, in_org, reserved


def start(meeting_id, user_id, name, size, org_id=""):
    if not 0 < size <= max_bytes():
        raise HTTPException(413, "recordings can be up to %d MB" % (max_bytes() // 1048576))
    mine, total, in_org, reserved = open_uploads(user_id, org_id)
    if mine >= 3 or in_org >= 5 or total >= 20:
        raise HTTPException(429, "too many uploads are in progress; finish or wait for the others first")
    os.makedirs(staging(), exist_ok=True)
    if shutil.disk_usage(staging()).free < size + reserved + 2 * 1024 ** 3:
        raise HTTPException(507, "the server is low on space for recordings; ask your IT office")
    uid = secrets.token_hex(16)
    path = staging(uid)
    os.makedirs(path)
    with open(os.path.join(path, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump({"meeting": meeting_id, "user": user_id, "org": org_id, "name": name[:200], "size": size, "at": time.time()}, fh)
    return uid


def meta(upload_id, meeting_id):
    path = os.path.join(staging(upload_id), "meta.json")
    try:
        with open(path, encoding="utf-8") as fh:
            m = json.load(fh)
    except FileNotFoundError:
        raise HTTPException(404, "upload not found or expired")
    if m["meeting"] != meeting_id:
        raise HTTPException(404, "upload not found")
    return m


def parts(m):
    return (m["size"] + CHUNK - 1) // CHUNK


async def write_part(request: Request, upload_id, meeting_id, index):
    m = meta(upload_id, meeting_id)
    if not 0 <= index < parts(m):
        raise HTTPException(400, "unexpected part number")
    expected = CHUNK if index < parts(m) - 1 else m["size"] - CHUNK * (parts(m) - 1)
    path = os.path.join(staging(upload_id), "part-%05d" % index)
    seen = 0
    with open(path + ".tmp", "wb") as fh:
        async for data in request.stream():
            seen += len(data)
            if seen > expected:
                raise HTTPException(413, "this part is larger than expected")
            fh.write(data)
    if seen != expected:
        os.remove(path + ".tmp")
        raise HTTPException(400, "this part was cut off; send it again")
    os.replace(path + ".tmp", path)
    return seen


def assemble(upload_id, meeting_id, org_id):
    m = meta(upload_id, meeting_id)
    folder = staging(upload_id)
    out = os.path.join(folder, "recording")
    with open(out, "wb") as dst:
        for i in range(parts(m)):
            part = os.path.join(folder, "part-%05d" % i)
            if not os.path.exists(part):
                raise HTTPException(400, "part %d is missing; send it again" % (i + 1))
            with open(part, "rb") as src:
                shutil.copyfileobj(src, dst, 1024 * 1024)
    if os.path.getsize(out) != m["size"]:
        raise HTTPException(400, "the upload is incomplete")
    try:
        return store_file(out, org_id, meeting_id, m["name"])
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def store_file(path, org_id, meeting_id, name):
    mime = sniff_file(path)
    if mime is None:
        raise HTTPException(400, "upload an MP4, M4A, MOV, WebM, MP3, WAV, or OGG recording")
    key = "orgs/%s/meetings/%s/recording.%s" % (org_id, meeting_id, EXT[mime])
    storage.store().put_file(key, path)
    return {"key": key, "type": mime, "size": os.path.getsize(path),
            "name": re.sub(r"[^\w.\- ]+", "_", os.path.basename(name or "recording"))[:200]}


def cleanup(max_age=86400):
    root = staging()
    if not os.path.isdir(root):
        return 0
    n = 0
    for uid in os.listdir(root):
        path = os.path.join(root, uid)
        try:
            try:
                with open(os.path.join(path, "meta.json"), encoding="utf-8") as fh:
                    began = float(json.load(fh).get("at") or 0)
            except (OSError, ValueError):
                began = os.path.getmtime(path)
            if time.time() - began > max_age:
                shutil.rmtree(path, ignore_errors=True)
                n += 1
        except FileNotFoundError:
            pass
    return n


class _Sink:
    def __init__(self):
        self.parts, self.pos = [], 0

    def write(self, data):
        self.parts.append(bytes(data))
        self.pos += len(data)
        return len(data)

    def tell(self):
        return self.pos

    def flush(self):
        return None

    def take(self):
        out, self.parts = b"".join(self.parts), []
        return out


def zip_stream(entries, extra=()):
    sink = _Sink()
    with zipfile.ZipFile(sink, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for name, data in extra:
            z.writestr(name, data)
        yield sink.take()
        for name, key, size in entries:
            info = zipfile.ZipInfo(name, time.gmtime()[:6])
            with z.open(info, "w", force_zip64=True) as fh:
                for chunk in storage.store().read_range(key, 0, size - 1):
                    fh.write(chunk)
                    data = sink.take()
                    if data:
                        yield data
            yield sink.take()
    yield sink.take()


def stream(request: Request, key, mime, filename, download=False):
    try:
        size = storage.store().size(key)
    except Exception:
        raise HTTPException(404, "recording not found")
    start, end, status = 0, size - 1, 200
    rng = request.headers.get("range", "")
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
    if m and (m.group(1) or m.group(2)):
        if m.group(1):
            start = int(m.group(1))
            end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
        else:
            start = max(0, size - int(m.group(2)))
        if start > end or start >= size:
            return Response(status_code=416, headers={"Content-Range": "bytes */%d" % size})
        end = min(end, start + 16 * 1024 * 1024 - 1) if not download else end
        status = 206
    headers = {"Accept-Ranges": "bytes", "Content-Length": str(end - start + 1), "Cache-Control": "private, max-age=300",
               "X-Content-Type-Options": "nosniff",
               "Content-Disposition": '%s; filename="%s"' % ("attachment" if download else "inline", filename)}
    if status == 206:
        headers["Content-Range"] = "bytes %d-%d/%d" % (start, end, size)
    return StreamingResponse(storage.store().read_range(key, start, end), status_code=status, media_type=mime,
                             headers=headers)
