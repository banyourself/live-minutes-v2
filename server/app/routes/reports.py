import datetime as dt
import os
import statistics

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, records, scope
from ..db import get_db
from ..deps import current_user, platform_admin

router = APIRouter(tags=["reports"])
DOCS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "procurement")
TITLES = {"hecvat-lite": "HECVAT Lite answers", "vpat-acr": "Accessibility conformance report (VPAT)",
          "ferpa-dpa": "FERPA data protection agreement", "subprocessors": "Subprocessors and data flow"}


def month_starts(months, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    y, m = now.year, now.month
    out = []
    for _ in range(months):
        out.append(dt.datetime(y, m, 1, tzinfo=dt.timezone.utc))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return list(reversed(out))


def build(db, orgs, months):
    ids = [o.id for o in orgs]
    starts = month_starts(months)
    edges = [s.timestamp() for s in starts] + [dt.datetime.now(dt.timezone.utc).timestamp() + 1]
    meetings = db.scalars(select(models.Meeting).where(models.Meeting.org_id.in_(ids or [""]))).all()
    usage = db.scalars(select(models.AIUsage).where(models.AIUsage.org_id.in_(ids or [""]),
                                                    models.AIUsage.created_at >= edges[0])).all()
    trans = db.scalars(select(models.MeetingTranslation).where(models.MeetingTranslation.org_id.in_(ids or [""]),
                                                              models.MeetingTranslation.created_at >= edges[0])).all()
    events = db.execute(select(models.AuditEvent.user_id, models.AuditEvent.org_id, models.AuditEvent.created_at)
                        .where(models.AuditEvent.org_id.in_(ids or [""]), models.AuditEvent.created_at >= edges[0])).all()
    names = {o.id: o.name for o in orgs}
    rows, per_org = [], {}
    for i, start in enumerate(starts):
        lo, hi = edges[i], edges[i + 1]
        held = [m for m in meetings if m.status in ("open", "ended", "approved") and lo <= (m.scheduled_at or m.created_at) < hi]
        approved = [m for m in meetings if m.approved_at and lo <= m.approved_at < hi]
        days = [max(0.0, (m.approved_at - (m.scheduled_at or m.created_at)) / 86400) for m in approved]
        used = [u for u in usage if lo <= u.created_at < hi]
        rows.append({"month": start.strftime("%Y-%m"), "meetings": len(held), "approved": len(approved),
                     "median_days_to_approve": round(statistics.median(days), 1) if days else None,
                     "active_orgs": len({m.org_id for m in held}),
                     "active_people": len({e.user_id for e in events if e.user_id and lo <= e.created_at < hi}),
                     "ai_calls": len(used), "ai_tokens": sum(u.input_tokens + u.output_tokens for u in used),
                     "ai_cents": round(sum(u.cost_cents for u in used), 2),
                     "translations": len([t for t in trans if lo <= t.created_at < hi])})
        for m in held:
            p = per_org.setdefault(m.org_id, {"org": names.get(m.org_id, ""), "meetings": 0, "approved": 0, "ai_cents": 0.0})
            p["meetings"] += 1
        for m in approved:
            per_org.setdefault(m.org_id, {"org": names.get(m.org_id, ""), "meetings": 0, "approved": 0, "ai_cents": 0.0})["approved"] += 1
        for u in used:
            if u.org_id in names:
                per_org.setdefault(u.org_id, {"org": names[u.org_id], "meetings": 0, "approved": 0, "ai_cents": 0.0})["ai_cents"] += u.cost_cents
    orgs_out = sorted(({**v, "ai_cents": round(v["ai_cents"], 2)} for v in per_org.values()), key=lambda r: (-r["meetings"], r["org"]))
    return {"months": rows, "orgs": orgs_out, "org_count": len(orgs)}


def clamp(months):
    if not 1 <= months <= 24:
        raise HTTPException(400, "choose 1 to 24 months")
    return months


def as_csv(data, filename):
    head = ["Month", "Meetings", "Minutes approved", "Median days to approve", "Active organizations", "Active people",
            "AI calls", "AI tokens", "AI cost (USD)", "Translations"]
    rows = [[r["month"], r["meetings"], r["approved"], "" if r["median_days_to_approve"] is None else r["median_days_to_approve"],
             r["active_orgs"], r["active_people"], r["ai_calls"], r["ai_tokens"], "%.2f" % (r["ai_cents"] / 100),
             r["translations"]] for r in data["months"]]
    return Response(records.to_csv(head, rows), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="%s"' % filename, "Cache-Control": "no-store"})


@router.get("/api/manage/{scope_name}/{target_id}/reports")
def scope_reports(scope_name: str, target_id: str, months: int = 6, format: str = "json",
                  user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = scope.resolve(db, user, scope_name, target_id)
    data = build(db, scope.orgs_in(db, ctx), clamp(months))
    return as_csv(data, "usage-report.csv") if format == "csv" else data


@router.get("/api/admin/reports")
def platform_reports(months: int = 6, format: str = "json", user: models.User = Depends(platform_admin),
                     db: Session = Depends(get_db)):
    data = build(db, db.scalars(select(models.Organization)).all(), clamp(months))
    return as_csv(data, "usage-report-all.csv") if format == "csv" else data


def can_read_docs(db, user):
    return user.is_platform_admin or bool(scope.scopes(db, user))


@router.get("/api/procurement")
def procurement_list(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if not can_read_docs(db, user):
        raise HTTPException(403, "procurement documents are for district IT, college IT, and the platform owner")
    return {"documents": [{"id": k, "title": v} for k, v in TITLES.items() if os.path.exists(os.path.join(DOCS, k + ".md"))]}


@router.get("/api/procurement/{doc_id}")
def procurement_doc(doc_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if not can_read_docs(db, user):
        raise HTTPException(403, "procurement documents are for district IT, college IT, and the platform owner")
    if doc_id not in TITLES:
        raise HTTPException(404, "document not found")
    with open(os.path.join(DOCS, doc_id + ".md"), encoding="utf-8") as fh:
        text = fh.read()
    return Response(text, media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="live-minutes-%s.md"' % doc_id})
