import argparse
import sys
import time

from sqlalchemy import select

from server.app import db, models
from server.app.routes.auth import issue_token
from server.app.security import reencrypt
from server.app.settings import settings


def find_user(s, email):
    user = s.scalar(select(models.User).where(models.User.email == email.strip().lower()))
    if user is None:
        sys.exit("no account for " + email)
    return user


def make_admin(args):
    email = args.email.strip().lower()
    raw = ""
    with db.SessionLocal() as s:
        user = s.scalar(select(models.User).where(models.User.email == email))
        if user is None:
            if not args.create:
                sys.exit("no account for %s (add --create to make one)" % email)
            user = models.User(email=email, name=args.name[:200])
            s.add(user)
            s.flush()
        user.is_platform_admin = True
        if user.email_verified_at is None:
            user.email_verified_at, user.verified_via = time.time(), "admin"
        if not user.password_hash:
            raw = issue_token(s, user, "reset", 24)
        s.add(models.AuditEvent(action="user.platform_admin", user_id=user.id, detail={"by": "manage"}))
        s.commit()
    print("%s is now a platform administrator" % email)
    if raw:
        print("Choose a password within 24 hours: %s/reset/%s" % (settings.public_url, raw))


def reset_link(args):
    with db.SessionLocal() as s:
        user = find_user(s, args.email)
        raw = issue_token(s, user, "reset", 1)
        s.add(models.AuditEvent(action="user.reset_link_issued", user_id=user.id, detail={"by": "manage"}))
        s.commit()
    print("%s/reset/%s" % (settings.public_url, raw))
    print("This link works once, for one hour. Send it to the person privately.")


def rotate_keys(_args):
    if not settings.encryption_keys:
        sys.exit("set ENCRYPTION_KEYS with the new key first")
    count = 0
    with db.SessionLocal() as s:
        for row in s.scalars(select(models.AIConnection)):
            row.api_key_enc = reencrypt(row.api_key_enc)
            count += 1
        for row in s.scalars(select(models.ZoomConnection)):
            row.token_enc = reencrypt(row.token_enc)
            count += 1
        s.commit()
    print("re-encrypted %d stored secrets with the first key in ENCRYPTION_KEYS" % count)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m server.manage")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("make-admin", help="make an account a platform administrator")
    p.add_argument("email")
    p.add_argument("--create", action="store_true", help="create the account if it does not exist")
    p.add_argument("--name", default="")
    p.set_defaults(fn=make_admin)
    p = sub.add_parser("reset-link", help="print a one-time password reset link for an account")
    p.add_argument("email")
    p.set_defaults(fn=reset_link)
    p = sub.add_parser("rotate-keys", help="re-encrypt stored secrets with the newest ENCRYPTION_KEYS entry")
    p.set_defaults(fn=rotate_keys)
    args = parser.parse_args(argv)
    settings.validate()
    db.init_db()
    args.fn(args)


if __name__ == "__main__":
    main()
