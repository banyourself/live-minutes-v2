import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import ai_runtime, audit, governance, models, officers, ratelimit, records
from ..db import get_db
from ..deps import client_ip, current_user, meeting_for, require_role
from .meetings import motions_for

router = APIRouter(tags=["records"])


class MotionIn(BaseModel):
    id: str = ""
    t: float | None = None
    under: str = ""
    text: str
    mover: str = ""
    seconder: str = ""
    method: str = "voice"
    result: str = ""
    votes: dict[str, str] = {}


class RecordIn(BaseModel):
    motions: list[MotionIn]


class FundingIn(BaseModel):
    title: str
    requester: str = ""
    amount: float
    purpose: str = ""


class FundingPatch(BaseModel):
    title: str | None = None
    requester: str | None = None
    amount: float | None = None
    purpose: str | None = None
    status: str | None = None
    approved_amount: float | None = None
    motion_id: str | None = None
    notes: str | None = None


class AskIn(BaseModel):
    question: str


def name(value):
    return " ".join((value or "").split())[:200]


def motion_row(r, meeting=None):
    row = {"id": r.id, "meeting_id": r.meeting_id, "position": r.position, "t": r.t, "under": r.under, "text": r.text,
           "mover": r.mover, "seconder": r.seconder, "method": r.method, "result": r.result, "votes": r.votes or {},
           "tally": records.tally(r.votes)}
    if meeting is not None:
        row.update(title=meeting.title, meeting_date=meeting.meeting_date, meeting_status=meeting.status)
    return row


def saved(db, meeting_id):
    return db.scalars(select(models.MotionRecord).where(models.MotionRecord.meeting_id == meeting_id)
                      .order_by(models.MotionRecord.position)).all()


@router.get("/api/meetings/{meeting_id}/record")
def get_record(meeting_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    mt, _, role = meeting_for(db, user, meeting_id, "viewer")
    rows = saved(db, mt.id)
    return {"motions": [motion_row(r) for r in rows], "detected": records.normalize_detected(motions_for(db, mt)),
            "saved": bool(rows), "editable": models.ROLE_RANK[role] >= models.ROLE_RANK["secretary"]
            and mt.status != "approved"}


@router.put("/api/meetings/{meeting_id}/record")
def put_record(meeting_id: str, body: RecordIn, request: Request, user: models.User = Depends(current_user),
               db: Session = Depends(get_db)):
    mt, org, _ = meeting_for(db, user, meeting_id, "secretary")
    if mt.status == "approved":
        raise HTTPException(400, "these minutes are approved; reopen them before changing motions")
    if {r.id for r in saved(db, mt.id)} - {m.id for m in body.motions if m.id}:
        governance.check_hold(db, org, "remove saved motions")
    if len(body.motions) > 200:
        raise HTTPException(400, "a meeting can have up to 200 motions")
    existing = {r.id: r for r in saved(db, mt.id)}
    keep = set()
    for i, m in enumerate(body.motions):
        text = (m.text or "").strip()[:2000]
        if not text:
            raise HTTPException(400, "motion %d needs its wording" % (i + 1))
        if m.method not in models.MOTION_METHODS:
            raise HTTPException(400, "unknown voting method")
        if m.result not in models.MOTION_RESULTS:
            raise HTTPException(400, "unknown motion result")
        if len(m.votes) > 300:
            raise HTTPException(400, "a motion can list up to 300 votes")
        votes = {}
        for who, v in m.votes.items():
            if v not in models.VOTE_VALUES:
                raise HTTPException(400, "votes must be yes, no, abstain, absent, or present")
            if name(who):
                votes[name(who)] = v
        r = existing.get(m.id)
        if r is None:
            r = models.MotionRecord(org_id=mt.org_id, meeting_id=mt.id)
            db.add(r)
        r.position, r.t, r.under, r.text = i, m.t, name(m.under)[:300], text
        r.mover, r.seconder, r.method, r.result, r.votes = name(m.mover), name(m.seconder), m.method, m.result, votes
        r.updated_by, r.updated_at = user.id, time.time()
        if r.id:
            keep.add(r.id)
    for rid, r in existing.items():
        if rid not in keep:
            db.delete(r)
    audit.log(db, "meeting.motions_saved", user, mt.org_id, client_ip(request), meeting=mt.id, count=len(body.motions))
    db.commit()
    return {"motions": [motion_row(r) for r in saved(db, mt.id)]}


def vote_rows(db, org_id):
    meetings = {m.id: m for m in db.scalars(select(models.Meeting).where(models.Meeting.org_id == org_id)).all()}
    rows = db.scalars(select(models.MotionRecord).where(models.MotionRecord.org_id == org_id)).all()
    rows = [r for r in rows if r.meeting_id in meetings]
    rows.sort(key=lambda r: (meetings[r.meeting_id].scheduled_at or meetings[r.meeting_id].created_at, r.position))
    return rows, meetings


def person_history(rows, meetings, who):
    key = who.lower()
    out = []
    for r in rows:
        vote = next((v for n, v in (r.votes or {}).items() if n.lower() == key), "")
        moved, seconded = r.mover.lower() == key, r.seconder.lower() == key
        if vote or moved or seconded:
            m = meetings[r.meeting_id]
            out.append({"meeting_id": m.id, "title": m.title, "meeting_date": m.meeting_date, "status": m.status,
                        "motion": r.text, "result": r.result, "vote": vote, "moved": moved, "seconded": seconded,
                        "motion_id": r.id})
    return out


@router.get("/api/orgs/{org_id}/votes")
def votes(org_id: str, person: str = "", user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, org_id, "viewer")
    rows, meetings = vote_rows(db, org_id)
    if person:
        return {"person": person, "history": person_history(rows, meetings, person)}
    people = {}
    for r in rows:
        for who, v in (r.votes or {}).items():
            p = people.setdefault(who.lower(), {"name": who, "yes": 0, "no": 0, "abstain": 0, "absent": 0,
                                                "present": 0, "moved": 0, "seconded": 0})
            p[v] = p.get(v, 0) + 1
        for field, who in (("moved", r.mover), ("seconded", r.seconder)):
            if who:
                p = people.setdefault(who.lower(), {"name": who, "yes": 0, "no": 0, "abstain": 0, "absent": 0,
                                                    "present": 0, "moved": 0, "seconded": 0})
                p[field] += 1
    return {"people": sorted(people.values(), key=lambda p: p["name"].lower()), "motions": len(rows)}


def csv_response(text, filename):
    return Response(text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="%s"' % filename,
                             "Cache-Control": "no-store"})


@router.get("/api/orgs/{org_id}/votes.csv")
def votes_csv(org_id: str, person: str = "", user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, org_id, "viewer")
    rows, meetings = vote_rows(db, org_id)
    audit.log(db, "votes.exported", user, org_id, person=person[:200])
    db.commit()
    if person:
        hist = person_history(rows, meetings, person)
        out = [[h["meeting_date"], h["title"], "approved" if h["status"] == "approved" else "draft", h["motion"],
                h["result"], h["vote"], "yes" if h["moved"] else "", "yes" if h["seconded"] else ""] for h in hist]
        slug = "".join(ch for ch in person if ch.isalnum() or ch in "-_")[:40] or "person"
        return csv_response(records.to_csv(["Meeting date", "Meeting", "Minutes", "Motion", "Result", "Vote", "Moved",
                                            "Seconded"], out), "voting-record-%s.csv" % slug)
    out = []
    for r in rows:
        m = meetings[r.meeting_id]
        for who in sorted(r.votes or {}, key=str.lower) or [""]:
            out.append([m.meeting_date, m.title, "approved" if m.status == "approved" else "draft", r.text, r.mover,
                        r.seconder, r.method.replace("_", " "), r.result, who, (r.votes or {}).get(who, "")])
    return csv_response(records.to_csv(["Meeting date", "Meeting", "Minutes", "Motion", "Moved by", "Seconded by",
                                        "Method", "Result", "Name", "Vote"], out), "voting-record.csv")


def can_fund(db, user, org):
    _, role = require_role(db, user, org.id, "member")
    return role == "owner" or officers.authority(db, user, org).has("manage_funding")


def cents(amount, label="amount"):
    if amount is None:
        return None
    if not 0 <= amount <= 10_000_000:
        raise HTTPException(400, "enter a %s between $0 and $10,000,000" % label)
    return int(round(amount * 100))


def funding_row(f, motion, meeting):
    return {"id": f.id, "title": f.title, "requester": f.requester, "amount_cents": f.amount_cents,
            "approved_cents": f.approved_cents, "purpose": f.purpose, "status": f.status, "notes": f.notes,
            "created_at": f.created_at, "decided_at": f.decided_at, "motion_id": f.motion_id,
            "motion": {"text": motion.text, "result": motion.result, "meeting_id": motion.meeting_id,
                       "meeting": meeting.title if meeting else "", "meeting_date": meeting.meeting_date if meeting else ""}
            if motion else None}


@router.get("/api/orgs/{org_id}/funding")
def funding(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "member")
    rows = db.scalars(select(models.FundingRequest).where(models.FundingRequest.org_id == org_id)
                      .order_by(models.FundingRequest.created_at.desc()).limit(500)).all()
    mrows, meetings = vote_rows(db, org_id)
    by_id = {r.id: r for r in mrows}
    totals = {"requested": 0, "approved": 0, "paid": 0, "pending": 0}
    for f in rows:
        totals["requested"] += f.amount_cents
        if f.status in ("approved", "paid"):
            totals["approved"] += f.approved_cents if f.approved_cents is not None else f.amount_cents
        if f.status == "paid":
            totals["paid"] += f.approved_cents if f.approved_cents is not None else f.amount_cents
        if f.status in ("submitted", "in_review"):
            totals["pending"] += f.amount_cents
    out = []
    for f in rows:
        mo = by_id.get(f.motion_id) if f.motion_id else None
        out.append(funding_row(f, mo, meetings.get(mo.meeting_id) if mo else None))
    recent = [motion_row(r, meetings[r.meeting_id]) for r in reversed(mrows[-150:])]
    return {"requests": out, "totals": totals, "can_manage": can_fund(db, user, org), "motions": recent}


@router.post("/api/orgs/{org_id}/funding")
def add_funding(org_id: str, body: FundingIn, request: Request, user: models.User = Depends(current_user),
                db: Session = Depends(get_db)):
    require_role(db, user, org_id, "member")
    ratelimit.hit("funding:" + user.id, 50, 86400)
    title = name(body.title)
    if len(title) < 2:
        raise HTTPException(400, "enter what the money is for")
    f = models.FundingRequest(org_id=org_id, title=title, requester=name(body.requester), amount_cents=cents(body.amount),
                              purpose=(body.purpose or "")[:4000], created_by=user.id)
    db.add(f)
    audit.log(db, "funding.created", user, org_id, client_ip(request), title=title, amount_cents=f.amount_cents)
    db.commit()
    return {"id": f.id}


@router.patch("/api/orgs/{org_id}/funding/{request_id}")
def edit_funding(org_id: str, request_id: str, body: FundingPatch, request: Request,
                 user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "member")
    f = db.get(models.FundingRequest, request_id)
    if f is None or f.org_id != org_id:
        raise HTTPException(404, "funding request not found")
    manage = can_fund(db, user, org)
    mine = f.created_by == user.id and f.status == "submitted"
    if not manage and not mine:
        raise HTTPException(403, "only the treasurer, advisor, or an owner can change this request")
    deciding = any(v is not None for v in (body.approved_amount, body.motion_id, body.notes))
    if not manage and (deciding or body.status not in (None, "withdrawn")):
        raise HTTPException(403, "only the treasurer, advisor, or an owner can decide on requests")
    if body.title is not None:
        if len(name(body.title)) < 2:
            raise HTTPException(400, "enter what the money is for")
        f.title = name(body.title)
    if body.requester is not None:
        f.requester = name(body.requester)
    if body.amount is not None:
        f.amount_cents = cents(body.amount)
    if body.purpose is not None:
        f.purpose = body.purpose[:4000]
    if body.notes is not None:
        f.notes = body.notes[:4000]
    if body.approved_amount is not None:
        f.approved_cents = cents(body.approved_amount, "approved amount")
    if body.motion_id is not None:
        if body.motion_id == "":
            f.motion_id = None
        else:
            mo = db.get(models.MotionRecord, body.motion_id)
            if mo is None or mo.org_id != org_id:
                raise HTTPException(400, "choose a motion from this organization's meetings")
            f.motion_id = mo.id
            if body.status is None and f.status in ("submitted", "in_review") and mo.result in ("passed", "failed"):
                f.status = "approved" if mo.result == "passed" else "denied"
                f.decided_at = time.time()
    if body.status is not None:
        if body.status not in models.FUNDING_STATES:
            raise HTTPException(400, "unknown status")
        if body.status != f.status:
            f.status = body.status
            f.decided_at = time.time() if body.status in ("approved", "denied", "paid") else f.decided_at
    f.updated_at = time.time()
    audit.log(db, "funding.updated", user, org_id, client_ip(request), request=f.id, status=f.status,
              motion=f.motion_id or "")
    db.commit()
    return {"ok": True, "status": f.status}


@router.delete("/api/orgs/{org_id}/funding/{request_id}")
def delete_funding(org_id: str, request_id: str, request: Request, user: models.User = Depends(current_user),
                   db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "member")
    f = db.get(models.FundingRequest, request_id)
    if f is None or f.org_id != org_id:
        raise HTTPException(404, "funding request not found")
    if not can_fund(db, user, org):
        raise HTTPException(403, "only the treasurer, advisor, or an owner can delete requests")
    governance.check_hold(db, org, "delete funding requests")
    audit.log(db, "funding.deleted", user, org_id, client_ip(request), title=f.title, amount_cents=f.amount_cents)
    db.delete(f)
    db.commit()
    return {"ok": True}


@router.get("/api/orgs/{org_id}/funding.csv")
def funding_csv(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    data = funding(org_id, user, db)
    rows = [[time.strftime("%Y-%m-%d", time.localtime(r["created_at"])), r["title"], r["requester"],
             "%.2f" % (r["amount_cents"] / 100), "" if r["approved_cents"] is None else "%.2f" % (r["approved_cents"] / 100),
             r["status"].replace("_", " "), (r["motion"] or {}).get("meeting_date", ""), (r["motion"] or {}).get("text", ""),
             (r["motion"] or {}).get("result", ""), r["purpose"]] for r in data["requests"]]
    return csv_response(records.to_csv(["Submitted", "Request", "Requested by", "Amount", "Approved amount", "Status",
                                        "Motion date", "Motion", "Motion result", "Purpose"], rows), "funding-requests.csv")


@router.get("/api/orgs/{org_id}/search")
def search(org_id: str, q: str = "", user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, org_id, "viewer")
    q = q.strip()[:200]
    if len(q) < 2:
        return {"results": []}
    return {"results": [records.result_row(c) for c in records.ranked(db, org_id, q, limit=50)]}


@router.post("/api/orgs/{org_id}/ask")
def ask(org_id: str, body: AskIn, request: Request, user: models.User = Depends(current_user),
        db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "member")
    question = " ".join((body.question or "").split())[:500]
    if len(question) < 5:
        raise HTTPException(400, "ask a full question")
    ratelimit.hit("ask:" + user.id, 40, 3600, "you asked many questions this hour; try again later")
    picked = records.excerpts(db, org_id, question)
    sources = [records.result_row(c, i) for i, c in enumerate(picked, 1)]
    if not picked:
        return {"answer": "", "sources": [], "note": "Nothing in this organization's minutes or transcripts matches "
                "those words yet. Try different words, or search instead."}
    text, conn = ai_runtime.ask(db, user, org, "questions", records.material(question, picked), max_tokens=600)
    audit.log(db, "ask.answered", user, org_id, client_ip(request), sources=len(sources), ai=conn.label)
    db.commit()
    return {"answer": text.strip(), "sources": sources, "ai": conn.label}
