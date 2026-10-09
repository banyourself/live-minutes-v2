from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import audit, governance, models, references
from ..db import get_db
from ..deps import client_ip, current_user, meeting_for

router = APIRouter(tags=["references"])


class ReferenceIn(BaseModel):
    label: str
    filename: str = ""
    text: str


def payload(row):
    return {"id": row.id, "label": row.label, "filename": row.filename, "chars": len(row.text),
            "lines": row.text.count("\n") + 1 if row.text else 0, "created_at": row.created_at}


@router.get("/api/meetings/{meeting_id}/references")
def list_references(meeting_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    mt, _, _ = meeting_for(db, user, meeting_id, "viewer")
    return {"references": [payload(r) for r in references.rows_for(db, mt.id)], "sources": list(references.SOURCES),
            "max": references.MAX_PER_MEETING}


@router.post("/api/meetings/{meeting_id}/references")
def add_reference(meeting_id: str, body: ReferenceIn, request: Request, user: models.User = Depends(current_user),
                  db: Session = Depends(get_db)):
    mt, _, _ = meeting_for(db, user, meeting_id, "secretary")
    if mt.status == "approved":
        raise HTTPException(400, "these minutes are approved; reopen them before adding a reference transcript")
    if body.label not in references.SOURCES:
        raise HTTPException(400, "choose which app the transcript came from")
    if len(body.text) > references.MAX_CHARS:
        raise HTTPException(413, "the reference transcript is too large")
    if len(references.rows_for(db, mt.id)) >= references.MAX_PER_MEETING:
        raise HTTPException(400, "a meeting can have up to %d reference transcripts; remove one first" % references.MAX_PER_MEETING)
    text = references.normalize(body.text)
    if len(text) < 20:
        raise HTTPException(400, "the reference transcript is empty")
    row = models.ReferenceTranscript(meeting_id=mt.id, label=body.label, filename=" ".join(body.filename.split())[:200],
                                     text=text, created_by=user.id)
    db.add(row)
    audit.log(db, "reference.added", user, mt.org_id, client_ip(request), meeting=mt.id, label=body.label, chars=len(text))
    db.commit()
    return payload(row)


@router.delete("/api/meetings/{meeting_id}/references/{reference_id}")
def remove_reference(meeting_id: str, reference_id: str, request: Request, user: models.User = Depends(current_user),
                     db: Session = Depends(get_db)):
    mt, org, _ = meeting_for(db, user, meeting_id, "secretary")
    governance.check_hold(db, org, "delete a reference transcript")
    row = db.get(models.ReferenceTranscript, reference_id)
    if row is None or row.meeting_id != mt.id:
        raise HTTPException(404, "reference transcript not found")
    audit.log(db, "reference.removed", user, mt.org_id, client_ip(request), meeting=mt.id, label=row.label)
    db.delete(row)
    db.commit()
    return {"ok": True}
