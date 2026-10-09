import base64
import glob
import os
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from . import audit, models
from .settings import settings

MAGIC = b"LMB1"
INFO = b"live-minutes offsite backup v1"
STATE = "offsite_backup"
PATTERNS = ("db-*.dump", "files-*.tar.gz")
CHECK_EVERY = 3600
_last_check = [0.0]


def configured():
    return all((settings.offsite_endpoint, settings.offsite_bucket, settings.offsite_key_id, settings.offsite_secret,
                settings.offsite_public_key))


def _key(shared, ephemeral):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=ephemeral, info=INFO).derive(shared)


def seal(data, public_b64):
    recipient = X25519PublicKey.from_public_bytes(base64.b64decode(public_b64))
    eph = X25519PrivateKey.generate()
    eph_pub = eph.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    nonce = os.urandom(12)
    return MAGIC + eph_pub + nonce + AESGCM(_key(eph.exchange(recipient), eph_pub)).encrypt(nonce, data, MAGIC + eph_pub)


def unseal(blob, private_b64):
    if blob[:4] != MAGIC:
        raise ValueError("not a Live Minutes offsite backup")
    eph_pub, nonce, body = blob[4:36], blob[36:48], blob[48:]
    me = X25519PrivateKey.from_private_bytes(base64.b64decode(private_b64))
    shared = me.exchange(X25519PublicKey.from_public_bytes(eph_pub))
    return AESGCM(_key(shared, eph_pub)).decrypt(nonce, body, MAGIC + eph_pub)


def new_keypair():
    me = X25519PrivateKey.generate()
    private = me.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    public = me.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(private).decode(), base64.b64encode(public).decode()


def client():
    import boto3
    from .backups import outbound, s3_host
    s3_host(settings.offsite_endpoint)
    outbound(settings.offsite_endpoint)
    return boto3.client("s3", endpoint_url=settings.offsite_endpoint, region_name="auto",
                        aws_access_key_id=settings.offsite_key_id, aws_secret_access_key=settings.offsite_secret)


def newest(pattern):
    found = sorted(glob.glob(os.path.join(settings.backups_dir, pattern)))
    return found[-1] if found else None


def prune(s3, now):
    cutoff = now - settings.offsite_keep_days * 86400
    removed = 0
    pages = s3.get_paginator("list_objects_v2").paginate(Bucket=settings.offsite_bucket, Prefix="live-minutes/")
    for page in pages:
        for obj in page.get("Contents", []):
            if obj["LastModified"].timestamp() < cutoff:
                s3.delete_object(Bucket=settings.offsite_bucket, Key=obj["Key"])
                removed += 1
    return removed


def run_due(db, now=None, force=False):
    now = time.time() if now is None else now
    if not configured() or (not force and now - _last_check[0] < CHECK_EVERY):
        return None
    _last_check[0] = now
    row = db.get(models.PlatformSetting, STATE)
    state = dict((row.value if row else None) or {})
    done = set(state.get("uploaded") or [])
    files = [p for p in (newest(x) for x in PATTERNS) if p and os.path.basename(p) not in done]
    if not files:
        return []
    sent = []
    try:
        s3 = client()
        for path in files:
            name = os.path.basename(path)
            with open(path, "rb") as fh:
                sealed = seal(fh.read(), settings.offsite_public_key)
            s3.put_object(Bucket=settings.offsite_bucket, Key="live-minutes/" + name + ".lmb", Body=sealed,
                          ContentType="application/octet-stream")
            sent.append(name)
            done.add(name)
        removed = prune(s3, now)
        state.update(uploaded=sorted(done)[-20:], last_at=now, last_error="")
        audit.log(db, "offsite.backup", None, None, "worker", files=",".join(sent), removed=removed)
    except Exception as exc:
        state.update(uploaded=sorted(done)[-20:], last_error=str(getattr(exc, "detail", exc))[:300], last_error_at=now)
        audit.log(db, "offsite.backup_failed", None, None, "worker", error=state["last_error"][:200])
    if row is None:
        db.add(models.PlatformSetting(key=STATE, value=state, updated_at=now))
    else:
        row.value, row.updated_at = state, now
    db.commit()
    return sent
