import time

from fastapi import HTTPException
from sqlalchemy import delete, func, select

from . import models
from .db import SessionLocal

MESSAGE = "too many attempts; wait a few minutes and try again"


def count(key, window):
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(models.RateEvent)
                         .where(models.RateEvent.key == key[:400],
                                models.RateEvent.created_at > time.time() - window)) or 0


def record(key):
    with SessionLocal() as db:
        db.add(models.RateEvent(key=key[:400], created_at=time.time()))
        db.commit()


def blocked(key, limit, window):
    return count(key, window) >= limit


def hit(key, limit, window, message=MESSAGE):
    if blocked(key, limit, window):
        raise HTTPException(429, message)
    record(key)


def clear(key):
    with SessionLocal() as db:
        db.execute(delete(models.RateEvent).where(models.RateEvent.key == key[:400]))
        db.commit()


def clear_prefix(prefix):
    with SessionLocal() as db:
        db.execute(delete(models.RateEvent).where(models.RateEvent.key >= prefix[:400],
                                                  models.RateEvent.key < prefix[:400] + "\uffff"))
        db.commit()


def purge(older_than=86400):
    with SessionLocal() as db:
        db.execute(delete(models.RateEvent).where(models.RateEvent.created_at < time.time() - older_than))
        db.commit()
