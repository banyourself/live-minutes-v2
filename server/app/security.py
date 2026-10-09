import base64
import hashlib
import hmac
import ipaddress
import secrets
import socket
import urllib.parse

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from .settings import settings

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1


def hash_password(password):
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return "scrypt$%d$%d$%d$%s$%s" % (SCRYPT_N, SCRYPT_R, SCRYPT_P,
                                     base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(password, stored):
    try:
        _, n, r, p, salt, dk = (stored or "").split("$")
        expect = base64.b64decode(dk)
        got = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt),
                             n=int(n), r=int(r), p=int(p), dklen=len(expect))
        return hmac.compare_digest(got, expect)
    except (ValueError, TypeError):
        return False


_dummy = []


def burn_password_check(password):
    if not _dummy:
        _dummy.append(hash_password(secrets.token_urlsafe(16)))
    verify_password(password, _dummy[0])
    return False


def new_token():
    return secrets.token_urlsafe(32)


def token_hash(token):
    return hashlib.sha256(("%s:%s" % (settings.secret_key, token)).encode("utf-8")).hexdigest()


def _fernet():
    derived = Fernet(base64.urlsafe_b64encode(hashlib.sha256(("fernet:" + settings.secret_key).encode("utf-8")).digest()))
    return MultiFernet([Fernet(k.encode("ascii")) for k in settings.encryption_keys] + [derived])


def reencrypt(blob):
    return _fernet().rotate(blob.encode("ascii")).decode("ascii") if blob else blob


def encrypt(text):
    if not text:
        return ""
    return _fernet().encrypt(text.encode("utf-8")).decode("ascii")


def decrypt(blob):
    if not blob:
        return ""
    try:
        return _fernet().decrypt(blob.encode("ascii")).decode("utf-8")
    except InvalidToken:
        raise ValueError("stored secret could not be decrypted (was SECRET_KEY changed?)")


def mask(secret):
    if not secret:
        return ""
    return "••••" + secret[-4:]


def ip_blocked(value):
    ip = ipaddress.ip_address(value.split("%", 1)[0])
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return not ip.is_global or ip.is_multicast


def public_address(url):
    parts = urllib.parse.urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("server URL must start with http:// or https://")
    if settings.allow_private_llm_urls:
        return None
    if parts.scheme != "https":
        raise ValueError("server URL must use https on this deployment")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError("could not resolve " + parts.hostname)
    addrs = [info[4][0] for info in infos]
    if not addrs or any(ip_blocked(a) for a in addrs):
        raise ValueError("server URL points to a private network address, which this deployment blocks")
    return addrs[0]


def check_outbound_url(url):
    public_address(url)
    return url
