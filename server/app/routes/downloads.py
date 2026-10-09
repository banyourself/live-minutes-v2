import hashlib
import os
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..settings import settings

router = APIRouter(tags=["downloads"])
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,120}\.(exe|zip)$")
UPDATE_FEED = "latest.yml"
_hashes: dict = {}


def folder():
    return os.path.realpath(os.path.join(settings.storage_dir, "downloads"))


def path_for(name):
    if not (NAME.match(name or "") or name == UPDATE_FEED):
        raise HTTPException(404, "not found")
    base = folder()
    path = os.path.realpath(os.path.join(base, name))
    if os.path.dirname(path) != base or not os.path.isfile(path):
        raise HTTPException(404, "not found")
    return path


def sha256(path):
    stat = os.stat(path)
    key = (path, stat.st_size, stat.st_mtime)
    if key not in _hashes:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        _hashes[key] = h.hexdigest()
    return _hashes[key]


@router.get("/api/downloads")
def list_downloads():
    base = folder()
    names = sorted(n for n in os.listdir(base) if NAME.match(n)) if os.path.isdir(base) else []
    out = []
    for name in names:
        path = path_for(name)
        out.append({"name": name, "size": os.path.getsize(path), "sha256": sha256(path)})
    return {"files": out}


@router.get("/api/downloads/{name}")
def get_download(name: str):
    path = path_for(name)
    if name == UPDATE_FEED:
        return FileResponse(path, media_type="text/yaml", headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})
    return FileResponse(path, filename=name, headers={"Cache-Control": "public, max-age=3600", "X-Content-Type-Options": "nosniff"})
