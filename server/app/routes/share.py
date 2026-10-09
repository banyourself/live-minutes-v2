import json
import os
import shutil
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from minutes_app import accessibility, drafter, guard, llm

from .. import ai_runtime, audit, governance, models, quick_translate, ratelimit, records, storage
from ..db import get_db
from ..deps import client_ip, current_user, meeting_for
from .meetings import download_name, export_data

router = APIRouter(tags=["share"])
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
LANGUAGES = {
    "es": ("Spanish", "es-US"), "vi": ("Vietnamese", "vi-VN"), "zh-Hans": ("Chinese (Simplified)", "zh-CN"),
    "zh-Hant": ("Chinese (Traditional)", "zh-TW"), "ko": ("Korean", "ko-KR"), "tl": ("Tagalog", "fil-PH"),
    "ar": ("Arabic", "ar-SA"), "fa": ("Persian", "fa-IR"), "hy": ("Armenian", "hy-AM"), "ru": ("Russian", "ru-RU"),
    "ja": ("Japanese", "ja-JP"), "pt": ("Portuguese", "pt-BR"), "fr": ("French", "fr-FR"), "hi": ("Hindi", "hi-IN"),
    "pa": ("Punjabi", "pa-IN"), "km": ("Khmer", "km-KH"), "en": ("English", "en-US"),
}


class TranslateIn(BaseModel):
    language: str
    engine: str = "ai"


def pieces(draft, plain=""):
    d = draft or {}
    out = {}
    for i, f in enumerate(d.get("fills") or []):
        if (f.get("text") or "").strip():
            out["f%d" % i] = f["text"]
    for i, m in enumerate(d.get("motions") or []):
        if (m.get("text") or "").strip():
            out["m%d" % i] = m["text"]
    for i, (_, v) in enumerate(sorted((d.get("reports") or {}).items())):
        if records.report_text(v).strip():
            out["r%d" % i] = records.report_text(v)
    for i, line in enumerate(d.get("summary") or []):
        if (line or "").strip():
            out["s%d" % i] = line
    for i, r in enumerate(d.get("replace") or []):
        if (r.get("text") or "").strip():
            out["p%d" % i] = r["text"]
    if (plain or "").strip():
        out["plain"] = plain
    return out


def apply(draft, done):
    d = json.loads(json.dumps(draft or {}))
    for i, f in enumerate(d.get("fills") or []):
        f["text"] = done.get("f%d" % i, f.get("text", ""))
    for i, m in enumerate(d.get("motions") or []):
        m["text"] = done.get("m%d" % i, m.get("text", ""))
    reports = d.get("reports") or {}
    for i, name in enumerate(sorted(reports)):
        if "r%d" % i in done:
            v = reports[name]
            reports[name] = dict(v, text=done["r%d" % i]) if isinstance(v, dict) else done["r%d" % i]
    d["summary"] = [done.get("s%d" % i, line) for i, line in enumerate(d.get("summary") or [])]
    if not d["summary"]:
        d.pop("summary")
    for i, r in enumerate(d.get("replace") or []):
        r["text"] = done.get("p%d" % i, r.get("text", ""))
    return d, done.get("plain", "")


def doc_title(org, mt):
    return ("%s minutes: %s %s" % (org.name, mt.title, mt.meeting_date)).strip()[:250]


def build(db, mt, draft, title, word_lang):
    tpl = db.get(models.Template, mt.template_id)
    if tpl is None:
        raise HTTPException(400, "this meeting's template is missing")
    tpl_key = tpl.storage_key
    work = storage.workdir()
    try:
        out = os.path.join(work, "minutes.docx")
        drafter.render(storage.store().local_copy(tpl_key, work), export_data(mt, draft or {}), out)
        accessibility.set_properties(out, title, word_lang)
        with open(out, "rb") as fh:
            data = fh.read()
        report = accessibility.check(out)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return data, report


def ai_budget(user):
    ratelimit.hit("ai-share:" + user.id, 30, 3600, "you asked for many translations and summaries this hour; try again later")


def translation_row(t, mt):
    name, _ = LANGUAGES.get(t.language, (t.language, ""))
    return {"language": t.language, "name": name, "summary": t.summary, "created_at": t.created_at, "ai": t.ai_label,
            "stale": t.source_rev != (mt.draft_rev or 0), "items": len(pieces(t.draft))}


@router.get("/api/meetings/{meeting_id}/translations")
def list_translations(meeting_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    mt, _, _ = meeting_for(db, user, meeting_id, "viewer")
    rows = db.scalars(select(models.MeetingTranslation).where(models.MeetingTranslation.meeting_id == mt.id)
                      .order_by(models.MeetingTranslation.language)).all()
    return {"translations": [translation_row(t, mt) for t in rows],
            "languages": [{"code": k, "name": v[0]} for k, v in LANGUAGES.items() if k != "en"],
            "quick": [k for k in LANGUAGES if k != "en" and quick_translate.supports(k)],
            "summary": {"text": mt.plain_summary, "at": mt.plain_summary_at,
                        "stale": bool(mt.plain_summary) and mt.plain_summary_rev != (mt.draft_rev or 0)}}


@router.post("/api/meetings/{meeting_id}/summary")
def write_summary(meeting_id: str, request: Request, user: models.User = Depends(current_user),
                  db: Session = Depends(get_db)):
    mt, org, _ = meeting_for(db, user, meeting_id, "secretary")
    parts = records.flatten_draft(mt.draft)
    motions = db.scalars(select(models.MotionRecord).where(models.MotionRecord.meeting_id == mt.id)
                         .order_by(models.MotionRecord.position)).all()
    if not parts and not motions:
        raise HTTPException(400, "there are no minutes to summarize yet")
    ai_budget(user)
    lines = ["Minutes of %s, %s, for %s." % (mt.title, mt.meeting_date or "no date", org.name), ""]
    lines += ["%s: %s" % (label, text) for label, text in parts]
    lines += ["Motion: %s (moved by %s, seconded by %s, %s)" % (m.text, m.mover or "unknown", m.seconder or "unknown",
                                                                m.result or "no result") for m in motions]
    text, conn = ai_runtime.ask(db, user, org, "summary", guard.data("minutes", "\n".join(lines), 30000), max_tokens=700)
    mt.plain_summary, mt.plain_summary_at, mt.plain_summary_rev = text.strip()[:6000], time.time(), mt.draft_rev or 0
    audit.log(db, "meeting.summarized", user, mt.org_id, client_ip(request), meeting=mt.id, ai=conn.label)
    db.commit()
    return {"text": mt.plain_summary, "at": mt.plain_summary_at, "stale": False}


@router.post("/api/meetings/{meeting_id}/translations")
def translate(meeting_id: str, body: TranslateIn, request: Request, user: models.User = Depends(current_user),
              db: Session = Depends(get_db)):
    mt, org, _ = meeting_for(db, user, meeting_id, "secretary")
    if body.language not in LANGUAGES or body.language == "en":
        raise HTTPException(400, "choose a language from the list")
    name, _ = LANGUAGES[body.language]
    items = pieces(mt.draft, mt.plain_summary)
    if not items:
        raise HTTPException(400, "there is nothing to translate yet")
    if body.engine == "quick":
        if not quick_translate.supports(body.language):
            raise HTTPException(400, "quick translation is not available for %s right now; use the AI translation" % name)
        ratelimit.hit("quick-translate:" + user.id, 30, 3600)
        try:
            done = quick_translate.translate(items, body.language)
        except (httpx.HTTPError, ValueError):
            raise HTTPException(502, "quick translation did not answer; try again or use the AI translation")
        label = quick_translate.LABEL
    else:
        ai_budget(user)
        text, conn = ai_runtime.ask(db, user, org, "translate", json.dumps(items, ensure_ascii=False),
                                    extra="Translate every value into %s. Return one JSON object with exactly the same keys "
                                          "and nothing else." % name, max_tokens=8000)
        try:
            done = llm.extract_json(text)
        except llm.LLMError as exc:
            raise HTTPException(502, "the AI's translation could not be read: %s" % str(exc)[:200])
        if not isinstance(done, dict) or set(done) != set(items) or not all(isinstance(v, str) for v in done.values()):
            raise HTTPException(502, "the AI's translation did not match the minutes; try again")
        label = conn.label
    draft, summary = apply(mt.draft, {k: v[:8000] for k, v in done.items()})
    row = db.scalar(select(models.MeetingTranslation).where(models.MeetingTranslation.meeting_id == mt.id,
                                                            models.MeetingTranslation.language == body.language))
    if row is None:
        row = models.MeetingTranslation(meeting_id=mt.id, org_id=mt.org_id, language=body.language, created_by=user.id)
        db.add(row)
    row.draft, row.summary, row.source_rev, row.ai_label = draft, summary, mt.draft_rev or 0, label[:200]
    row.created_by, row.created_at = user.id, time.time()
    audit.log(db, "meeting.translated", user, mt.org_id, client_ip(request), meeting=mt.id, language=body.language,
              ai=label)
    db.commit()
    return translation_row(row, mt)


@router.delete("/api/meetings/{meeting_id}/translations/{language}")
def delete_translation(meeting_id: str, language: str, request: Request, user: models.User = Depends(current_user),
                       db: Session = Depends(get_db)):
    mt, org, _ = meeting_for(db, user, meeting_id, "secretary")
    row = db.scalar(select(models.MeetingTranslation).where(models.MeetingTranslation.meeting_id == mt.id,
                                                            models.MeetingTranslation.language == language))
    if row is not None:
        governance.check_hold(db, org, "remove translations")
        db.delete(row)
        audit.log(db, "meeting.translation_removed", user, mt.org_id, client_ip(request), meeting=mt.id, language=language)
        db.commit()
    return {"ok": True}


@router.get("/api/meetings/{meeting_id}/translations/{language}/minutes.docx")
def translated_docx(meeting_id: str, language: str, user: models.User = Depends(current_user),
                    db: Session = Depends(get_db)):
    mt, org, _ = meeting_for(db, user, meeting_id, "member")
    row = db.scalar(select(models.MeetingTranslation).where(models.MeetingTranslation.meeting_id == mt.id,
                                                            models.MeetingTranslation.language == language))
    if row is None:
        raise HTTPException(404, "translate the minutes into this language first")
    name, tag = LANGUAGES.get(language, (language, "en-US"))
    data, _ = build(db, mt, row.draft, doc_title(org, mt) + " (%s)" % name, tag)
    filename = download_name(mt, "docx").replace(".docx", "-%s.docx" % language)
    return Response(data, media_type=DOCX, headers={"Content-Disposition": 'attachment; filename="%s"' % filename})


@router.get("/api/meetings/{meeting_id}/accessibility")
def check_accessibility(meeting_id: str, language: str = "en", user: models.User = Depends(current_user),
                        db: Session = Depends(get_db)):
    mt, org, _ = meeting_for(db, user, meeting_id, "member")
    draft, tag = mt.draft, "en-US"
    if language != "en":
        row = db.scalar(select(models.MeetingTranslation).where(models.MeetingTranslation.meeting_id == mt.id,
                                                                models.MeetingTranslation.language == language))
        if row is None:
            raise HTTPException(404, "translate the minutes into this language first")
        draft, tag = row.draft, LANGUAGES.get(language, ("", "en-US"))[1]
    _, report = build(db, mt, draft, doc_title(org, mt), tag)
    return report
