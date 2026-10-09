import difflib
import re
import time

from sqlalchemy import func, select

from . import governance, models, records

KEEP = 300
TOKEN = re.compile(r"\s+|\w+|[^\w\s]")


def record(db, mt, before, source, user=None, label=""):
    after = mt.draft or {}
    if (before or {}) == after:
        return None
    count = db.scalar(select(func.count()).select_from(models.DraftRevision)
                      .where(models.DraftRevision.meeting_id == mt.id))
    now = time.time()
    if not count and before:
        db.add(models.DraftRevision(meeting_id=mt.id, rev=max((mt.draft_rev or 1) - 1, 0), draft=before,
                                    source="earlier", label="The draft before history was kept", created_at=now - 1))
    row = models.DraftRevision(meeting_id=mt.id, rev=mt.draft_rev or 0, draft=after, source=source,
                               user_id=user.id if user is not None else None, label=(label or "")[:200], created_at=now)
    db.add(row)
    db.flush()
    if governance.holds_for(db, db.get(models.Organization, mt.org_id)):
        return row
    old = db.scalars(select(models.DraftRevision.id).where(models.DraftRevision.meeting_id == mt.id)
                     .order_by(models.DraftRevision.created_at.desc()).offset(KEEP)).all()
    for rid in old:
        db.delete(db.get(models.DraftRevision, rid))
    return row


def lines(draft):
    return records.flatten_draft(draft)


def words(a, b):
    ta, tb = TOKEN.findall(a or ""), TOKEN.findall(b or "")
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(["same", "".join(ta[i1:i2])])
            continue
        if i2 > i1:
            out.append(["del", "".join(ta[i1:i2])])
        if j2 > j1:
            out.append(["add", "".join(tb[j1:j2])])
    return out


def compare(old, new):
    a, b = lines(old), lines(new)
    sm = difflib.SequenceMatcher(None, [x[0] + "\x00" + x[1] for x in a], [x[0] + "\x00" + x[1] for x in b],
                                 autojunk=False)
    rows, added, removed = [], 0, 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            rows += [{"type": "same", "label": label, "text": text} for label, text in a[i1:i2]]
            continue
        olds, news = a[i1:i2], b[j1:j2]
        paired = min(len(olds), len(news)) if op == "replace" else 0
        for (la, ta), (lb, tb) in zip(olds[:paired], news[:paired]):
            rows.append({"type": "change", "label": lb, "old_label": la, "words": words(ta, tb)})
            added += 1
            removed += 1
        for label, text in olds[paired:]:
            rows.append({"type": "del", "label": label, "text": text})
            removed += 1
        for label, text in news[paired:]:
            rows.append({"type": "add", "label": label, "text": text})
            added += 1
    return {"rows": rows, "added": added, "removed": removed}
