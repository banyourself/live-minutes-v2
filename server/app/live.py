import time

from sqlalchemy import func, select

from minutes_app.transcript import Transcript

from . import models

WINDOW = 80


def recent_rows(db, meeting_id, limit=WINDOW):
    rows = db.scalars(select(models.TranscriptLine).where(models.TranscriptLine.meeting_id == meeting_id)
                      .order_by(models.TranscriptLine.seq.desc()).limit(limit)).all()
    return list(reversed(rows))


def line_count(db, meeting_id):
    return db.scalar(select(func.count()).select_from(models.TranscriptLine)
                     .where(models.TranscriptLine.meeting_id == meeting_id)) or 0


def _as_dicts(rows):
    return [{"id": r.id, "t": r.t, "speaker": r.speaker, "text": r.text, "source": r.source} for r in rows]


def _persist(db, meeting, before, tr):
    originals = {r.id: r for r in before}
    next_seq = (before[-1].seq + 1) if before else line_count(db, meeting.id)
    added = 0
    for ln in tr.lines:
        if ln.id is None:
            db.add(models.TranscriptLine(meeting_id=meeting.id, seq=next_seq, t=ln.t, speaker=ln.speaker or "",
                                         text=ln.text, source=ln.source))
            next_seq += 1
            added += 1
        else:
            row = originals.get(ln.id)
            if row is not None and row.text != ln.text:
                row.text = ln.text
                row.updated_at = time.time()
    return added


def ingest_snapshot(db, meeting, text):
    before = recent_rows(db, meeting.id)
    tr = Transcript.from_list(_as_dicts(before))
    tr.started = meeting.created_at
    tr._snapshot_tail = list(meeting.snapshot_tail or [])
    tr.ingest_snapshot(text[-60000:])
    meeting.snapshot_tail = tr._snapshot_tail
    meeting.updated_at = time.time()
    return _persist(db, meeting, before, tr)


def ingest_lines(db, meeting, lines, source="captions"):
    before = recent_rows(db, meeting.id)
    tr = Transcript.from_list(_as_dicts(before))
    tr.started = meeting.created_at
    for ln in lines:
        tr.add(str(ln.get("speaker", ""))[:200], str(ln.get("text", ""))[:4000], source, t=ln.get("t"))
    meeting.updated_at = time.time()
    return _persist(db, meeting, before, tr)


def import_text(db, meeting, text, filename=""):
    tr = Transcript()
    kind, n = tr.import_any(text, filename)
    existing = db.scalars(select(models.TranscriptLine).where(models.TranscriptLine.meeting_id == meeting.id)).all()
    merged = [(r.t, r.seq, r) for r in existing]
    for i, ln in enumerate(tr.lines):
        merged.append((ln.t, 10 ** 9 + i, models.TranscriptLine(
            meeting_id=meeting.id, seq=0, t=ln.t, speaker=ln.speaker or "", text=ln.text, source=ln.source)))
    merged.sort(key=lambda x: (x[0] is None, x[0] or 0, x[1]))
    for seq, (_, _, row) in enumerate(merged):
        row.seq = seq
        if row.id is None:
            db.add(row)
    meeting.drafted_upto = 0
    meeting.updated_at = time.time()
    return kind, n


def transcript_for(db, meeting_id, start=0):
    rows = db.scalars(select(models.TranscriptLine).where(models.TranscriptLine.meeting_id == meeting_id)
                      .order_by(models.TranscriptLine.seq)).all()
    return Transcript.from_list(_as_dicts(rows)), rows
