import shutil
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from minutes_app import drafter

from .. import audit, history, models, storage
from ..db import get_db
from ..deps import client_ip, current_user, meeting_for

router = APIRouter(prefix="/api/meetings/{meeting_id}/history", tags=["draft history"])
SOURCES = {"ai": "AI draft", "person": "Edited", "app": "Saved by an AI app", "restore": "Restored", "earlier": "Earlier draft"}


def revisions(db, meeting_id):
    return db.scalars(select(models.DraftRevision).where(models.DraftRevision.meeting_id == meeting_id)
                      .order_by(models.DraftRevision.created_at.desc())).all()


def revision_in(db, meeting_id, rev_id):
    row = db.get(models.DraftRevision, rev_id)
    if row is None or row.meeting_id != meeting_id:
        raise HTTPException(404, "version not found")
    return row


def who(db, row):
    if row.source == "ai":
        return row.label or "AI"
    if row.source == "app":
        return row.label or "AI app"
    u = db.get(models.User, row.user_id) if row.user_id else None
    return (u.name or u.email) if u else ""


@router.get("")
def list_history(meeting_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    mt, _, role = meeting_for(db, user, meeting_id)
    rows = revisions(db, mt.id)
    out = []
    for i, r in enumerate(rows):
        prev = rows[i + 1].draft if i + 1 < len(rows) else {}
        stats = history.compare(prev, r.draft)
        out.append({"id": r.id, "rev": r.rev, "source": r.source, "kind": SOURCES.get(r.source, r.source),
                    "who": who(db, r), "label": r.label if r.source in ("restore", "earlier") else "",
                    "created_at": r.created_at, "added": stats["added"], "removed": stats["removed"],
                    "current": i == 0 and r.draft == (mt.draft or {})})
    return {"versions": out, "draft_rev": mt.draft_rev or 0, "can_restore": role in ("secretary", "owner")
            and mt.status != "approved"}


@router.get("/compare")
def compare(meeting_id: str, base: str, head: str = "current", user: models.User = Depends(current_user),
            db: Session = Depends(get_db)):
    mt, _, _ = meeting_for(db, user, meeting_id)
    old = {} if base == "empty" else revision_in(db, mt.id, base).draft
    new = (mt.draft or {}) if head == "current" else revision_in(db, mt.id, head).draft
    return history.compare(old, new)


@router.post("/{rev_id}/restore")
def restore(meeting_id: str, rev_id: str, request: Request, user: models.User = Depends(current_user),
            db: Session = Depends(get_db)):
    mt, _, _ = meeting_for(db, user, meeting_id, "secretary")
    if mt.status == "approved":
        raise HTTPException(400, "these minutes are approved; reopen them before restoring an older version")
    row = revision_in(db, mt.id, rev_id)
    if row.draft == (mt.draft or {}):
        raise HTTPException(400, "this version is already the current draft")
    before = mt.draft or {}
    tpl = db.get(models.Template, mt.template_id)
    work = storage.workdir()
    try:
        mt.problems = drafter.check(storage.store().local_copy(tpl.storage_key, work), row.draft) if tpl else []
    finally:
        shutil.rmtree(work, ignore_errors=True)
    mt.draft = dict(row.draft)
    mt.draft_rev = (mt.draft_rev or 0) + 1
    mt.updated_at = time.time()
    if mt.review_status == "reviewed":
        mt.review_status, mt.review_note = "", "Edited after review; send it for review again."
    stamp = time.strftime("%b %d, %Y %H:%M UTC", time.gmtime(row.created_at))
    history.record(db, mt, before, "restore", user, "Restored the version from " + stamp)
    audit.log(db, "meeting.draft_restored", user, mt.org_id, client_ip(request), meeting=mt.id, version=row.id)
    db.commit()
    return {"ok": True, "draft_rev": mt.draft_rev}
