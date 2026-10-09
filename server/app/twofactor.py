import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

from .security import decrypt, token_hash

STEP = 30
DIGITS = 6
WINDOW = 1
RECOVERY_COUNT = 10
RECOVERY_LETTERS = "abcdefghjkmnpqrstuvwxyz23456789"
ISSUER = "Live Minutes"


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def code_at(secret, step):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10 ** DIGITS).zfill(DIGITS)


def matching_step(secret, code, after=0, now=None):
    digits = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(digits) != DIGITS:
        return None
    current = int((time.time() if now is None else now) // STEP)
    for step in range(current - WINDOW, current + WINDOW + 1):
        if step > after and hmac.compare_digest(code_at(secret, step), digits):
            return step
    return None


def uri(email, secret):
    label = urllib.parse.quote(ISSUER + ":" + email)
    return "otpauth://totp/%s?%s" % (label, urllib.parse.urlencode(
        {"secret": secret, "issuer": ISSUER, "algorithm": "SHA1", "digits": DIGITS, "period": STEP}))


def clean_recovery(code):
    return "".join(ch for ch in (code or "").lower() if ch.isalnum())


def new_recovery_codes():
    plain = []
    for _ in range(RECOVERY_COUNT):
        raw = "".join(secrets.choice(RECOVERY_LETTERS) for _ in range(10))
        plain.append(raw[:5] + "-" + raw[5:])
    return plain, [token_hash(clean_recovery(code)) for code in plain]


def check(user, code):
    if not user.totp_enabled_at or not user.totp_secret_enc:
        return None
    step = matching_step(decrypt(user.totp_secret_enc), code, user.totp_last_step or 0)
    if step is not None:
        user.totp_last_step = step
        return "app"
    cleaned = clean_recovery(code)
    hashed = token_hash(cleaned)
    remaining = list(user.recovery_codes or [])
    if len(cleaned) == 10 and hashed in remaining:
        remaining.remove(hashed)
        user.recovery_codes = remaining
        return "recovery"
    return None


def clear(user):
    user.totp_secret_enc, user.totp_pending_enc, user.totp_enabled_at = "", "", None
    user.totp_last_step, user.recovery_codes = 0, []
