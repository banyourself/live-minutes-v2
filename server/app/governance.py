import json
import os
import re
import shutil
import time
import zipfile

from fastapi import HTTPException
from sqlalchemy import delete, or_, select

from . import audit, models, officers, records, storage
from .db import SessionLocal

DAY = 86400
EXPORT_DAYS = 7
LIMITS = {"unapproved_days": (30, 3650), "transcript_days": (30, 3650), "approved_years": (1, 50)}
SECRET_KEYS = ("api_key", "token", "secret", "password")


def retention(district):
    cfg = (district.settings or {}).get("retention") or {}
    return {k: int(cfg.get(k) or 0) for k in LIMITS}


def clean_retention(body):
    out = {}
    for k, (lo, hi) in LIMITS.items():
        v = int(body.get(k) or 0)
        if v and not lo <= v <= hi:
            raise HTTPException(400, "%s must be 0 (keep forever) or between %d and %d" % (k.replace("_", " "), lo, hi))
        out[k] = v
    return out


def active_holds(db, district_id=None):
    q = select(models.LegalHold).where(models.LegalHold.released_at.is_(None))
    if district_id:
        q = q.where(models.LegalHold.district_id == district_id)
    return db.scalars(q).all()


def holds_for(db, org):
    return [h for h in active_holds(db, org.district_id)
            if (h.scope == "district" and h.target_id == org.district_id)
            or (h.scope == "school" and org.school_id and h.target_id == org.school_id)
            or (h.scope == "org" and h.target_id == org.id)]


def check_hold(db, org, what="delete these records"):
    if holds_for(db, org):
        raise HTTPException(409, "%s is under a legal hold; you cannot %s until district IT releases it" % (org.name, what))


ORG_RULES = ("advisors_create_orgs", "allow_org_delete")


def org_rules_for(db, school_id, district_id):
    district = db.get(models.District, district_id) if district_id else None
    school = db.get(models.School, school_id) if school_id else None
    dist = (district.settings or {}).get("org_rules", {}) if district else {}
    sch = (school.settings or {}).get("org_rules", {}) if school else {}
    return {k: bool(sch[k]) if k in sch else bool(dist.get(k, False)) for k in ORG_RULES}


def delete_org(db, org):
    ids = db.scalars(select(models.Meeting.id).where(models.Meeting.org_id == org.id)).all()
    if ids:
        db.execute(delete(models.TranscriptLine).where(models.TranscriptLine.meeting_id.in_(ids)))
        db.execute(delete(models.ReferenceTranscript).where(models.ReferenceTranscript.meeting_id.in_(ids)))
        db.execute(delete(models.Job).where(models.Job.meeting_id.in_(ids)))
        db.execute(delete(models.DraftRevision).where(models.DraftRevision.meeting_id.in_(ids)))
        db.execute(delete(models.Meeting).where(models.Meeting.id.in_(ids)))
    db.execute(delete(models.Template).where(models.Template.org_id == org.id))
    storage.store().delete_prefix("orgs/%s" % org.id)
    db.delete(org)


def remove_meeting(db, mt):
    db.execute(delete(models.TranscriptLine).where(models.TranscriptLine.meeting_id == mt.id))
    db.execute(delete(models.ReferenceTranscript).where(models.ReferenceTranscript.meeting_id == mt.id))
    db.execute(delete(models.Job).where(models.Job.meeting_id == mt.id))
    db.execute(delete(models.DraftRevision).where(models.DraftRevision.meeting_id == mt.id))
    storage.store().delete_prefix("orgs/%s/meetings/%s" % (mt.org_id, mt.id))
    db.delete(mt)


def candidates(db, district, at=None):
    at = time.time() if at is None else at
    cfg = retention(district)
    orgs = db.scalars(select(models.Organization).where(models.Organization.district_id == district.id)).all()
    out = {"unapproved": [], "transcripts": [], "approved": [], "held": 0}
    for org in orgs:
        meetings = db.scalars(select(models.Meeting).where(models.Meeting.org_id == org.id)).all()
        if holds_for(db, org):
            out["held"] += len(meetings)
            continue
        for m in meetings:
            if cfg["approved_years"] and m.status == "approved" and m.approved_at and \
                    m.approved_at < at - cfg["approved_years"] * 365 * DAY:
                out["approved"].append(m)
            elif cfg["unapproved_days"] and m.status in ("open", "ended") and \
                    (m.updated_at or m.created_at) < at - cfg["unapproved_days"] * DAY:
                out["unapproved"].append(m)
            elif cfg["transcript_days"] and m.status == "approved" and m.approved_at and \
                    m.approved_at < at - cfg["transcript_days"] * DAY:
                if db.scalar(select(models.TranscriptLine.id).where(models.TranscriptLine.meeting_id == m.id).limit(1)) or \
                        db.scalar(select(models.ReferenceTranscript.id).where(models.ReferenceTranscript.meeting_id == m.id).limit(1)):
                    out["transcripts"].append(m)
    return out


def preview(db, district, at=None):
    c = candidates(db, district, at)
    return {"unapproved_meetings": len(c["unapproved"]), "transcripts": len(c["transcripts"]),
            "approved_meetings": len(c["approved"]), "held_meetings": c["held"]}


def purge(db, at=None):
    at = time.time() if at is None else at
    total = {"unapproved": 0, "transcripts": 0, "approved": 0}
    for district in db.scalars(select(models.District)).all():
        if not any(retention(district).values()):
            continue
        c = candidates(db, district, at)
        for m in c["unapproved"] + c["approved"]:
            remove_meeting(db, m)
        for m in c["transcripts"]:
            db.execute(delete(models.TranscriptLine).where(models.TranscriptLine.meeting_id == m.id))
            db.execute(delete(models.ReferenceTranscript).where(models.ReferenceTranscript.meeting_id == m.id))
            m.snapshot_tail = []
        counts = {k: len(c[k]) for k in total}
        if any(counts.values()):
            audit.log(db, "retention.purged", None, district_id=district.id, **counts)
        for k in total:
            total[k] += counts[k]
    return total


def slug(text, fallback="item"):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:60] or fallback


def scrub(value):
    if isinstance(value, dict):
        return {k: ("[removed]" if any(s in k.lower() for s in SECRET_KEYS) else scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def export_orgs(db, job):
    if job.scope == "district":
        return db.scalars(select(models.Organization).where(models.Organization.district_id == job.target_id)
                          .order_by(models.Organization.name)).all()
    if job.scope == "school":
        return db.scalars(select(models.Organization).where(models.Organization.school_id == job.target_id)
                          .order_by(models.Organization.name)).all()
    return [o for o in [db.get(models.Organization, job.target_id)] if o is not None]


DATA_KINDS = {
    "minutes": "Minutes, motions, votes, reviews, and summaries, with Word files",
    "transcripts": "Meeting transcripts",
    "translations": "Translations",
    "members": "Members and officer terms",
    "funding": "Funding requests",
    "templates": "Templates",
    "activity": "Activity logs",
}


def kind_of(name):
    if name in ("members.csv", "officer_terms.csv"):
        return "members"
    if name == "funding.csv":
        return "funding"
    if name == "activity.csv":
        return "activity"
    if name.startswith("templates/"):
        return "templates"
    if "/translations/" in name:
        return "translations"
    if name.endswith("/transcript.txt"):
        return "transcripts"
    if name.endswith("/meeting.json") or name.endswith("/minutes.docx"):
        return "minutes"
    return ""


def write_org(db, z, org, root, counts, include=None):
    def w(name, data):
        kind = kind_of(name)
        if include is not None and kind and kind not in include:
            return
        z.writestr(root + name, data if isinstance(data, (bytes, str)) else json.dumps(data, indent=2, default=str))
    cfg = scrub(dict(org.settings or {}))
    w("organization.json", {"id": org.id, "name": org.name, "school": org.school, "district_id": org.district_id,
                            "school_id": org.school_id, "created_at": org.created_at, "settings": cfg})
    rows = db.execute(select(models.Membership, models.User).join(models.User, models.User.id == models.Membership.user_id)
                      .where(models.Membership.org_id == org.id)).all()
    titles = {}
    for t, p in db.execute(officers.active_query(org.id)).all():
        titles.setdefault(t.user_id, []).append(p.name)
    w("members.csv", records.to_csv(["Name", "Email", "Account type", "Role", "Positions", "Joined"],
                                    [[u.name, u.email, u.account_type, m.role, "; ".join(titles.get(u.id, [])),
                                      time.strftime("%Y-%m-%d", time.gmtime(m.created_at))] for m, u in rows]))
    terms = db.execute(select(models.PositionTerm, models.Position).join(models.Position, models.Position.id == models.PositionTerm.position_id)
                       .where(models.PositionTerm.org_id == org.id)).all()
    people = {u.id: u for _, u in rows}
    w("officer_terms.csv", records.to_csv(["Position", "Person", "Starts", "Ends", "Ended", "Reason"], [
        [p.name, (people.get(t.user_id).email if people.get(t.user_id) else t.user_id),
         time.strftime("%Y-%m-%d", time.gmtime(t.starts_at)), time.strftime("%Y-%m-%d", time.gmtime(t.ends_at)) if t.ends_at else "",
         time.strftime("%Y-%m-%d", time.gmtime(t.ended_at)) if t.ended_at else "", t.end_reason] for t, p in terms]))
    funds = db.scalars(select(models.FundingRequest).where(models.FundingRequest.org_id == org.id)).all()
    w("funding.csv", records.to_csv(["Submitted", "Request", "Requested by", "Amount", "Approved", "Status", "Motion", "Purpose"], [
        [time.strftime("%Y-%m-%d", time.gmtime(f.created_at)), f.title, f.requester, "%.2f" % (f.amount_cents / 100),
         "" if f.approved_cents is None else "%.2f" % (f.approved_cents / 100), f.status, f.motion_id or "", f.purpose] for f in funds]))
    events = db.scalars(select(models.AuditEvent).where(models.AuditEvent.org_id == org.id).order_by(models.AuditEvent.id)).all()
    w("activity.csv", records.to_csv(["When", "User", "Action", "Details"], [
        [time.strftime("%Y-%m-%d %H:%M", time.gmtime(e.created_at)), e.user_id or "", e.action,
         json.dumps(scrub(e.detail or {}), default=str)] for e in events]))
    for t in db.scalars(select(models.Template).where(models.Template.org_id == org.id)).all():
        try:
            w("templates/%s-%s.docx" % (slug(t.name, "template"), t.id[:6]), storage.store().get(t.storage_key))
        except Exception:
            pass
    meetings = db.scalars(select(models.Meeting).where(models.Meeting.org_id == org.id).order_by(models.Meeting.created_at)).all()
    for m in meetings:
        when = time.strftime("%Y-%m-%d", time.gmtime(m.scheduled_at or m.created_at))
        base = "meetings/%s-%s-%s/" % (when, slug(m.title, "meeting"), m.id[:6])
        motions = db.scalars(select(models.MotionRecord).where(models.MotionRecord.meeting_id == m.id)
                             .order_by(models.MotionRecord.position)).all()
        w(base + "meeting.json", {
            "id": m.id, "title": m.title, "meeting_date": m.meeting_date, "status": m.status, "notes": m.notes,
            "scheduled_at": m.scheduled_at, "created_at": m.created_at, "approved_at": m.approved_at,
            "approved_by": m.approved_by, "review": {"status": m.review_status, "note": m.review_note,
                                                     "reviewed_by": m.reviewed_by, "reviewed_at": m.reviewed_at},
            "zoom_url": m.zoom_url, "location": m.location, "draft": m.draft, "plain_summary": m.plain_summary,
            "motions": [{"text": r.text, "under": r.under, "mover": r.mover, "seconder": r.seconder, "method": r.method,
                         "result": r.result, "votes": r.votes} for r in motions]})
        lines = db.scalars(select(models.TranscriptLine).where(models.TranscriptLine.meeting_id == m.id)
                           .order_by(models.TranscriptLine.seq)).all()
        if lines:
            w(base + "transcript.txt", "\n".join(("%s: %s" % (ln.speaker, ln.text)) if ln.speaker else ln.text for ln in lines))
        for n, ref in enumerate(db.scalars(select(models.ReferenceTranscript).where(models.ReferenceTranscript.meeting_id == m.id)
                                           .order_by(models.ReferenceTranscript.created_at)).all(), 1):
            w(base + "references/%d.txt" % n, "From %s (%s)\n\n%s" % (ref.label, ref.filename or "pasted", ref.text))
        if m.export_key:
            try:
                w(base + "minutes.docx", storage.store().get(m.export_key))
            except Exception:
                pass
        for tr in db.scalars(select(models.MeetingTranslation).where(models.MeetingTranslation.meeting_id == m.id)).all():
            w(base + "translations/%s.json" % tr.language, {"language": tr.language, "draft": tr.draft, "summary": tr.summary})
        counts["meetings"] += 1
    counts["orgs"] += 1
    counts["members"] += len(rows)


def build_zip(db, scope_name, target_id, include=None):
    work = storage.workdir()
    try:
        path = os.path.join(work, "export.zip")
        counts = {"orgs": 0, "meetings": 0, "members": 0}
        target = db.get(models.District if scope_name == "district" else models.School, target_id) \
            if scope_name in ("district", "school") else db.get(models.Organization, target_id)
        job = models.ExportJob(scope=scope_name, target_id=target_id)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for org in export_orgs(db, job):
                write_org(db, z, org, "%s-%s/" % (slug(org.name, "organization"), org.id[:6]), counts, include)
            z.writestr("manifest.json", json.dumps({"scope": scope_name, "target": target.name if target else target_id,
                                                     "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                                     "counts": counts, "included": sorted(include) if include is not None
                                                     else sorted(DATA_KINDS),
                                                     "excluded": "AI keys, capture tokens, and Zoom tokens"}, indent=2))
        with open(path, "rb") as fh:
            return fh.read(), counts
    finally:
        shutil.rmtree(work, ignore_errors=True)


def build(db, job):
    data, counts = build_zip(db, job.scope, job.target_id)
    key = "exports/%s.zip" % job.id
    storage.store().put(key, data)
    return key, len(data), counts


def run_exports(at=None):
    at = time.time() if at is None else at
    db = SessionLocal()
    try:
        job = db.scalar(select(models.ExportJob).where(models.ExportJob.status == "queued")
                        .order_by(models.ExportJob.created_at).limit(1))
        if job is not None:
            job.status = "running"
            db.commit()
            try:
                job.storage_key, job.size, job.counts = build(db, job)
                job.status, job.finished_at, job.expires_at = "done", time.time(), time.time() + EXPORT_DAYS * DAY
                audit.log(db, "export.ready", None, export=job.id, scope=job.scope, target=job.target_id, size=job.size)
            except Exception as exc:
                db.rollback()
                job = db.get(models.ExportJob, job.id)
                job.status, job.error, job.finished_at = "error", str(exc)[:500], time.time()
            db.commit()
        old = db.scalars(select(models.ExportJob).where(models.ExportJob.status == "done",
                                                        models.ExportJob.expires_at < at)).all()
        for j in old:
            if j.storage_key:
                storage.store().delete(j.storage_key)
            j.status, j.storage_key = "expired", ""
        db.commit()
        return job is not None
    finally:
        db.close()


def move_holds(db, source_district, target_district):
    for h in db.scalars(select(models.LegalHold).where(or_(models.LegalHold.district_id == source_district.id))).all():
        h.district_id = target_district.id
        if h.scope == "district" and h.target_id == source_district.id:
            h.target_id = target_district.id
