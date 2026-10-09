import smtplib
import ssl
import time
import traceback
from email.message import EmailMessage

from sqlalchemy import select

from . import models
from .db import SessionLocal
from .settings import settings

MAX_ATTEMPTS = 6


def queue(db, to_addr, subject, body):
    db.add(models.OutboxEmail(to_addr=to_addr, subject=subject[:300], body=body))


def _send_smtp(msg):
    context = ssl.create_default_context()
    if settings.smtp_port == 465:
        server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30, context=context)
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
    try:
        server.ehlo()
        if settings.smtp_port != 465 and settings.smtp_starttls:
            server.starttls(context=context)
            server.ehlo()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except smtplib.SMTPException:
            pass


def _deliver(row):
    if settings.mail_backend == "console":
        print("\n[mail] to %s: %s\n%s\n" % (row.to_addr, row.subject, row.body), flush=True)
        return
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = row.to_addr
    msg["Subject"] = row.subject
    msg.set_content(row.body)
    _send_smtp(msg)


def deliver_pending(limit=20):
    if settings.mail_backend == "none":
        return 0
    sent = 0
    with SessionLocal() as db:
        rows = db.scalars(select(models.OutboxEmail).where(models.OutboxEmail.sent_at.is_(None),
                                                           models.OutboxEmail.attempts < MAX_ATTEMPTS,
                                                           models.OutboxEmail.next_try_at <= time.time())
                          .order_by(models.OutboxEmail.created_at).limit(limit)).all()
        for row in rows:
            row.attempts += 1
            try:
                _deliver(row)
                row.sent_at, row.error, row.body = time.time(), "", ""
                sent += 1
            except Exception as exc:
                row.error = str(exc)[:500]
                row.next_try_at = time.time() + 60 * (2 ** row.attempts)
                traceback.print_exc()
            db.commit()
    return sent
