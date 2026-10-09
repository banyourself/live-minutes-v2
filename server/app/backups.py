import json
import re
import time
import urllib.parse

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from . import audit, governance, models
from .db import SessionLocal
from .security import check_outbound_url, decrypt, encrypt
from .settings import settings

MAX_TARGETS = 5
DAY = 86400
EVERY = {"daily": DAY - 3600, "weekly": 7 * DAY - 3600}
AZURE_HOSTS = (".blob.core.windows.net", ".blob.core.usgovcloudapi.net")
S3_HOSTS = (".amazonaws.com", ".r2.cloudflarestorage.com", ".backblazeb2.com", ".wasabisys.com",
            ".digitaloceanspaces.com", ".storage.googleapis.com", ".linodeobjects.com")
BUCKET = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]$")
PREFIX = re.compile(r"^[A-Za-z0-9/_.\-]{0,200}$")
REGION = re.compile(r"^[a-z0-9\-]{0,40}$")


def outbound(url):
    try:
        return check_outbound_url(url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


def s3_host(url):
    parts = urllib.parse.urlparse(url)
    host = (parts.hostname or "").lower()
    allowed = S3_HOSTS + tuple("." + h.lstrip(".") for h in settings.backup_s3_hosts)
    if parts.scheme != "https" or not ("." + host).endswith(allowed):
        raise HTTPException(400, "use an https address from a known storage provider (Amazon S3, Cloudflare R2, Backblaze, "
                                 "Wasabi, DigitalOcean, Google Cloud, Linode); the platform owner can allow others")


def clean_prefix(value):
    value = (value or "").strip().strip("/")
    if not PREFIX.match(value):
        raise HTTPException(400, "the folder can use letters, numbers, slashes, dots, dashes, and underscores")
    return value


def clean(kind, body, old_secret=None):
    if kind not in models.BACKUP_KINDS:
        raise HTTPException(400, "choose S3-compatible storage or Azure Blob Storage")
    old = json.loads(decrypt(old_secret)) if old_secret else {}
    if kind == "s3":
        endpoint = (body.get("endpoint") or "").strip().rstrip("/")
        if endpoint:
            s3_host(endpoint)
            outbound(endpoint)
        bucket = (body.get("bucket") or "").strip()
        if not BUCKET.match(bucket):
            raise HTTPException(400, "enter a valid bucket name")
        region = (body.get("region") or "").strip().lower()
        if not REGION.match(region):
            raise HTTPException(400, "enter a region like us-west-2, or leave it empty")
        key_id = (body.get("access_key_id") or old.get("access_key_id") or "").strip()
        secret = (body.get("secret_access_key") or old.get("secret_access_key") or "").strip()
        if not key_id or not secret:
            raise HTTPException(400, "enter the access key ID and secret access key")
        config = {"endpoint": endpoint, "bucket": bucket, "region": region, "prefix": clean_prefix(body.get("prefix")),
                  "key_hint": key_id[-4:]}
        return config, encrypt(json.dumps({"access_key_id": key_id, "secret_access_key": secret}))
    url = (body.get("container_url") or "").strip().split("?", 1)[0].rstrip("/")
    parts = urllib.parse.urlparse(url)
    if parts.scheme != "https" or not (parts.hostname or "").endswith(AZURE_HOSTS) or parts.path.count("/") != 1:
        raise HTTPException(400, "enter the container URL, like https://account.blob.core.windows.net/minutes-backups")
    outbound(url)
    sas = (body.get("sas_token") or old.get("sas_token") or "").strip().lstrip("?")
    if "sig=" not in sas or "sv=" not in sas:
        raise HTTPException(400, "paste a container SAS token with create and write permission")
    return {"container_url": url, "prefix": clean_prefix(body.get("prefix"))}, encrypt(json.dumps({"sas_token": sas}))


def clean_kinds(kinds):
    out = sorted(set(kinds or []))
    if not out or any(k not in governance.DATA_KINDS for k in out):
        raise HTTPException(400, "choose at least one kind of data to back up")
    return out


def object_name(target, label, at):
    stamp = time.strftime("%Y-%m-%d-%H%M", time.gmtime(at))
    prefix = target.config.get("prefix") or ""
    return (prefix + "/" if prefix else "") + "live-minutes/%s-%s/%s.zip" % (target.scope, governance.slug(label, "backup"), stamp)


def upload(target, key, data, content_type="application/zip"):
    secret = json.loads(decrypt(target.secret))
    if target.kind == "s3":
        import boto3
        if target.config.get("endpoint"):
            s3_host(target.config["endpoint"])
            outbound(target.config["endpoint"])
        client = boto3.client("s3", endpoint_url=target.config.get("endpoint") or None,
                              region_name=target.config.get("region") or "us-east-1",
                              aws_access_key_id=secret["access_key_id"], aws_secret_access_key=secret["secret_access_key"])
        client.put_object(Bucket=target.config["bucket"], Key=key, Body=data, ContentType=content_type)
        return
    url = target.config["container_url"] + "/" + urllib.parse.quote(key) + "?" + secret["sas_token"]
    outbound(target.config["container_url"])
    r = httpx.put(url, content=data, timeout=900, follow_redirects=False,
                  headers={"x-ms-blob-type": "BlockBlob", "x-ms-version": "2021-08-06", "Content-Type": content_type})
    if r.status_code >= 300:
        raise RuntimeError("Azure answered %d: %s" % (r.status_code, r.text[:200]))


def label_for(db, target):
    row = db.get(models.District if target.scope == "district" else models.School, target.target_id)
    return row.name if row else target.target_id


def try_connection(db, target):
    key = ((target.config.get("prefix") or "") + "/" if target.config.get("prefix") else "") + "live-minutes/connection-test.txt"
    try:
        upload(target, key, ("Live Minutes can write here. %s\n" % time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())).encode(),
               "text/plain")
    except HTTPException:
        raise
    except Exception as exc:
        code = getattr(exc, "response", None)
        code = code.get("Error", {}).get("Code", "") if isinstance(code, dict) else ""
        raise HTTPException(400, "could not write to this storage%s; check the address, bucket, region, and keys" % (
            " (%s)" % code[:60] if code else ""))
    return key


def schedule_due(db, at=None):
    at = time.time() if at is None else at
    made = 0
    for t in db.scalars(select(models.BackupTarget).where(models.BackupTarget.active.is_(True))).all():
        if t.schedule not in EVERY or (t.last_run_at and at - t.last_run_at < EVERY[t.schedule]):
            continue
        busy = db.scalar(select(models.BackupRun.id).where(models.BackupRun.backup_id == t.id,
                                                           models.BackupRun.status.in_(("queued", "running"))))
        if busy:
            continue
        db.add(models.BackupRun(backup_id=t.id, trigger="schedule"))
        t.last_run_at = at
        made += 1
    return made


def run_backups():
    db = SessionLocal()
    try:
        run = db.scalar(select(models.BackupRun).where(models.BackupRun.status == "queued")
                        .order_by(models.BackupRun.created_at).limit(1))
        if run is None:
            return False
        target = db.get(models.BackupTarget, run.backup_id)
        run.status = "running"
        db.commit()
        try:
            data, counts = governance.build_zip(db, target.scope, target.target_id, set(target.data_kinds or []))
            key = object_name(target, label_for(db, target), time.time())
            upload(target, key, data)
            run.status, run.object_key, run.size = "done", key, len(data)
            audit.log(db, "backup.done", None, backup=target.id, scope=target.scope, target=target.target_id, size=len(data),
                      **counts)
        except Exception as exc:
            db.rollback()
            run = db.get(models.BackupRun, run.id)
            run.status, run.error = "error", (exc.detail if isinstance(exc, HTTPException) else str(exc))[:500]
            audit.log(db, "backup.failed", None, backup=run.backup_id, error=run.error[:200])
        run.finished_at = time.time()
        db.commit()
        return True
    finally:
        db.close()
