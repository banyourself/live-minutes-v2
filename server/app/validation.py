import hashlib
import re

import httpx
from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException

from . import runtime

DISPOSABLE = {
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "sharklasers.com", "10minutemail.com",
    "temp-mail.org", "tempmail.com", "yopmail.com", "trashmail.com", "getnada.com", "maildrop.cc",
    "dispostable.com", "throwawaymail.com", "fakeinbox.com", "mintemail.com", "mohmal.com", "emailondeck.com",
}
FREE_PROVIDERS = {
    "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "outlook.com", "hotmail.com", "live.com",
    "msn.com", "icloud.com", "me.com", "mac.com", "aol.com", "proton.me", "protonmail.com", "gmx.com",
    "gmx.net", "zoho.com", "yandex.com", "mail.com", "hey.com", "fastmail.com", "tutanota.com", "pm.me",
}
COMMON = {
    "password", "passw0rd", "qwerty", "qwertyuiop", "asdfghjkl", "zxcvbnm", "letmein", "welcome", "iloveyou",
    "admin", "administrator", "monkey", "dragon", "football", "baseball", "basketball", "soccer", "sunshine",
    "princess", "master", "shadow", "superman", "batman", "trustno", "whatever", "freedom", "starwars",
    "changeme", "secret", "default", "login", "student", "school", "college", "teacher", "minutes",
    "liveminutes", "coastline", "zoom", "summer", "winter", "spring", "autumn", "abc", "abcd", "abcdef",
    "hello", "love", "pass", "fall", "january", "february", "march", "april", "june", "july", "august",
    "september", "october", "november", "december", "monday", "friday", "sunday", "flower", "computer",
    "michael", "jessica", "jordan", "hunter", "ranger", "charlie", "pepper", "ginger", "cookie", "chocolate",
    "money", "family", "angel", "orange", "purple", "yellow", "silver", "golden", "access", "office",
    "district", "senate", "council", "government", "asg", "meeting", "agenda",
}
YEAR = re.compile(r"(19|20)\d\d")
SEQUENCES = ("abcdefghijklmnopqrstuvwxyz", "qwertyuiopasdfghjklzxcvbnm", "01234567890")


def clean_email(raw, check_dns=None):
    value = (raw or "").strip()
    if len(value) > 254:
        raise HTTPException(400, "that email address is too long")
    try:
        result = validate_email(value, check_deliverability=bool(runtime.get("email_dns_check")) if check_dns is None else check_dns,
                                allow_smtputf8=False, allow_quoted_local=False, allow_domain_literal=False)
    except EmailNotValidError as exc:
        raise HTTPException(400, "enter a valid email address (%s)" % str(exc).rstrip("."))
    email = result.normalized.lower()
    if result.domain.lower() in DISPOSABLE:
        raise HTTPException(400, "use a permanent email address, not a disposable one")
    return email


def email_domain(email):
    return email.rsplit("@", 1)[-1].lower()


def is_free_provider(email):
    return email_domain(email) in FREE_PROVIDERS


def _classes(pw):
    return sum(bool(re.search(p, pw)) for p in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]"))


def _has_sequence(lowered, size=5):
    for seq in SEQUENCES:
        for i in range(len(seq) - size + 1):
            chunk = seq[i:i + size]
            if chunk in lowered or chunk[::-1] in lowered:
                return True
    return False


def password_problems(pw, email="", name=""):
    problems = []
    minimum = int(runtime.get("password_min_length"))
    if len(pw) < minimum:
        problems.append("use at least %d characters" % minimum)
    if len(pw) > 256:
        problems.append("use at most 256 characters")
    need = 2 if len(pw) >= 20 else 3
    if _classes(pw) < need:
        problems.append("mix lowercase, uppercase, numbers, and symbols (three kinds), or use a passphrase "
                        "of 20 or more characters")
    lowered = pw.lower()
    letters = re.sub(r"[^a-z]", "", lowered)
    if lowered in COMMON or letters in COMMON or lowered.strip("0123456789!@#$%^&*.") in COMMON:
        problems.append("this is a very common password")
    remainder = YEAR.sub("", lowered)
    for word in sorted((w for w in COMMON if len(w) >= 4), key=len, reverse=True):
        remainder = remainder.replace(word, "")
    remainder = re.sub(r"(.)\1+", r"\1", re.sub(r"[^a-z0-9]", "", remainder))
    if len(remainder) < 6 and "this is a very common password" not in problems:
        problems.append("it is built around a common word or year; add more of your own words")
    if re.search(r"(.)\1\1\1", pw):
        problems.append("do not repeat the same character four times in a row")
    if _has_sequence(lowered):
        problems.append("avoid runs like 12345, abcde, or qwert")
    local = email.split("@", 1)[0].lower() if email else ""
    parts = [p for p in re.split(r"[^a-z0-9]+", local + " " + (name or "").lower()) if len(p) >= 3]
    if any(p in lowered for p in parts):
        problems.append("do not include your name or email in your password")
    return problems


def breached(pw):
    if not runtime.get("password_breach_check"):
        return False
    digest = hashlib.new("sha1", pw.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    try:
        resp = httpx.get("https://api.pwnedpasswords.com/range/" + digest[:5], timeout=4,
                         headers={"Add-Padding": "true", "User-Agent": "LiveMinutes"})
        resp.raise_for_status()
    except httpx.HTTPError:
        return False
    for line in resp.text.splitlines():
        suffix, _, count = line.partition(":")
        if suffix.strip() == digest[5:] and count.strip() not in ("", "0"):
            return True
    return False


def check_password(pw, email="", name=""):
    problems = password_problems(pw, email, name)
    if problems:
        raise HTTPException(400, "Password: " + "; ".join(problems) + ".")
    if breached(pw):
        raise HTTPException(400, "Password: this password has appeared in a known data breach; choose another.")
