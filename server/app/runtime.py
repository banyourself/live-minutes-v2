import threading
import time

from fastapi import HTTPException
from sqlalchemy import select

from . import models
from .db import SessionLocal
from .settings import settings

SPECS = {
    "allow_signup": {"type": "bool", "label": "Anyone can create an account", "group": "Accounts"},
    "allow_personal_signup": {"type": "bool", "default": True, "group": "Accounts",
                              "label": "Anyone can create a personal workspace (when sign-up is open)"},
    "personal_storage_mb": {"type": "int", "default": 2048, "min": 100, "max": 51200, "group": "Accounts",
                            "label": "Recording storage for each personal workspace, in MB"},
    "allow_district_creation": {"type": "bool", "label": "Users may add new districts without approval",
                                "group": "Accounts"},
    "maintenance_mode": {"type": "bool", "default": False, "group": "Accounts",
                         "label": "Maintenance mode (only platform administrators can sign in)"},
    "turnstile_required": {"type": "bool", "default": True, "group": "Sign-in protection",
                           "label": "Require the Cloudflare Turnstile check (when keys are configured)"},
    "lock_short": {"type": "int", "default": 5, "min": 3, "max": 10, "group": "Sign-in protection",
                   "label": "Failed sign-ins before a 15 minute pause"},
    "lock_day": {"type": "int", "default": 20, "min": 10, "max": 50, "group": "Sign-in protection",
                 "label": "Failed sign-ins in a day before the account locks"},
    "password_min_length": {"type": "int", "default": 12, "min": 12, "max": 64, "group": "Passwords",
                            "label": "Minimum password length"},
    "password_breach_check": {"type": "bool", "group": "Passwords",
                              "label": "Refuse passwords found in known data breaches"},
    "email_dns_check": {"type": "bool", "group": "Passwords", "label": "Refuse email domains that cannot receive mail"},
    "session_idle_hours": {"type": "float", "min": 1, "max": 72, "group": "Sessions",
                           "label": "Sign out after this many idle hours"},
    "session_days": {"type": "int", "min": 1, "max": 30, "group": "Sessions", "label": "Longest session, in days"},
    "invite_days": {"type": "int", "min": 1, "max": 30, "group": "Sessions", "label": "Invite links work for this many days"},
    "capture_token_days": {"type": "int", "min": 7, "max": 365, "group": "Sessions",
                           "label": "Capture device tokens expire after this many days"},
    "live_lines": {"type": "int", "min": 5, "max": 200, "group": "Drafting",
                   "label": "Redraft live minutes after this many new caption lines"},
    "live_seconds": {"type": "int", "min": 30, "max": 900, "group": "Drafting",
                     "label": "Or after this many seconds with new lines"},
}
HEARTBEAT = "worker_heartbeat"
TTL = 15
_lock = threading.Lock()
_cache = {"at": 0.0, "values": {}}


def default(name):
    spec = SPECS[name]
    return spec["default"] if "default" in spec else getattr(settings, name)


def _overrides():
    now = time.time()
    with _lock:
        if now - _cache["at"] < TTL:
            return _cache["values"]
    try:
        with SessionLocal() as db:
            rows = db.scalars(select(models.PlatformSetting).where(models.PlatformSetting.key.in_(list(SPECS)))).all()
            values = {r.key: r.value for r in rows}
    except Exception:
        values = {}
    with _lock:
        _cache["at"], _cache["values"] = now, values
    return values


def invalidate():
    with _lock:
        _cache["at"] = 0.0


def get(name):
    values = _overrides()
    return values[name] if name in values else default(name)


def coerce(name, raw):
    spec = SPECS.get(name)
    if spec is None:
        raise HTTPException(400, "unknown setting " + name)
    try:
        if spec["type"] == "bool":
            if not isinstance(raw, bool):
                raise ValueError()
            return raw
        value = int(raw) if spec["type"] == "int" else float(raw)
    except (TypeError, ValueError):
        raise HTTPException(400, "%s needs a %s value" % (spec["label"], spec["type"]))
    if value < spec["min"] or value > spec["max"]:
        raise HTTPException(400, "%s must be between %s and %s" % (spec["label"], spec["min"], spec["max"]))
    return value


def describe():
    values = _overrides()
    out = []
    for name, spec in SPECS.items():
        out.append({"key": name, "label": spec["label"], "group": spec["group"], "type": spec["type"],
                    "min": spec.get("min"), "max": spec.get("max"), "value": get(name), "default": default(name),
                    "overridden": name in values})
    return out


def save(db, changes, user_id):
    clean = {name: coerce(name, raw) for name, raw in changes.items()}
    for name, value in clean.items():
        row = db.get(models.PlatformSetting, name)
        if value == default(name):
            if row is not None:
                db.delete(row)
            continue
        if row is None:
            row = models.PlatformSetting(key=name)
            db.add(row)
        row.value, row.updated_at, row.updated_by = value, time.time(), user_id
    return clean


def heartbeat():
    try:
        with SessionLocal() as db:
            row = db.get(models.PlatformSetting, HEARTBEAT)
            if row is None:
                row = models.PlatformSetting(key=HEARTBEAT)
                db.add(row)
            row.value, row.updated_at = time.time(), time.time()
            db.commit()
    except Exception:
        pass


def last_heartbeat():
    with SessionLocal() as db:
        row = db.get(models.PlatformSetting, HEARTBEAT)
        return float(row.value) if row is not None and row.value else 0.0
