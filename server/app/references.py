import re

from sqlalchemy import select

from minutes_app.config import zm

from . import models

SOURCES = ("Otter", "Fireflies", "Fathom", "tl;dv", "Read.ai", "Microsoft Teams", "Google Meet", "Other")
MAX_PER_MEETING = 3
MAX_CHARS = 2_000_000
PROMPT_CHARS = 40_000
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
VOICE = re.compile(r"<v(?:\.[^ >]*)?\s+([^>]{1,60})>")
TAGS = re.compile(r"</?[a-zA-Z][^>]{0,40}>")


def clock(seconds):
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return "%d:%02d:%02d" % (hours, minutes, secs) if hours else "%d:%02d" % (minutes, secs)


def normalize(text):
    text = CONTROL.sub("", (text or "").replace("\r\n", "\n").replace("\r", "\n"))
    if "-->" in text[:5000]:
        cues = zm.parse_vtt(TAGS.sub("", VOICE.sub(r"\1: ", text)))
        if cues:
            return "\n".join("[%s] %s%s" % (clock(start), (speaker + ": ") if speaker else "", said)
                             for start, _, speaker, said in cues)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def rows_for(db, meeting_id):
    return db.scalars(select(models.ReferenceTranscript).where(models.ReferenceTranscript.meeting_id == meeting_id)
                      .order_by(models.ReferenceTranscript.created_at)).all()


def for_prompt(db, meeting_id):
    parts, left = [], PROMPT_CHARS
    for row in rows_for(db, meeting_id):
        if left <= 0:
            break
        chunk = row.text[:left]
        parts.append("From %s:\n%s" % (row.label, chunk))
        left -= len(chunk)
    return "\n\n".join(parts)
