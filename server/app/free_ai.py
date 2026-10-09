import contextvars
import time

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update

from . import models
from .db import SessionLocal

NAMES = {"gemma4:e4b": "Gemma 4", "qwen3.5:4b": "Qwen 3.5"}
SPEED_KEY = "free_ai_speed"
DEFAULT_SPEED = {"read": 16.0, "write": 4.0}
KNOWN_SPEED = {"gemma4:e4b": {"read": 14.7, "write": 4.7}, "qwen3.5:4b": {"read": 19.0, "write": 3.0}}
EXPECTED = {"minutes": 1800, "summary": 350, "assistant": 250, "questions": 350}
CHARS_PER_TOKEN = 3.2
CHECKPOINT = 15
ACTIVE = ("queued", "running")
PER_USER = 2
KEEP = 24 * 3600
TASK_LABELS = {"minutes": "Drafting minutes", "translate": "Translating", "summary": "Writing a summary",
               "assistant": "Answering", "questions": "Answering your question"}
current_run = contextvars.ContextVar("free_ai_run", default="")


class Pending(Exception):
    def __init__(self, payload):
        super().__init__("pending")
        self.payload = payload


def name_for(model):
    return NAMES.get(model, model)


def speeds(db, model):
    row = db.get(models.PlatformSetting, SPEED_KEY)
    learned = ((row.value if row else None) or {}).get(model) or {}
    base = KNOWN_SPEED.get(model, DEFAULT_SPEED)
    return {"read": float(learned.get("read") or base["read"]), "write": float(learned.get("write") or base["write"])}


def learn(model, prompt_tokens, prompt_seconds, output_tokens, output_seconds):
    if prompt_tokens < 200 or prompt_seconds <= 0:
        return
    with SessionLocal() as s:
        row = s.get(models.PlatformSetting, SPEED_KEY)
        data = dict((row.value if row else None) or {})
        old = speeds(s, model)
        read = prompt_tokens / prompt_seconds
        write = output_tokens / output_seconds if output_tokens >= 20 and output_seconds > 0 else old["write"]
        data[model] = {"read": round(0.7 * old["read"] + 0.3 * read, 2), "write": round(0.7 * old["write"] + 0.3 * write, 2)}
        if row is None:
            s.add(models.PlatformSetting(key=SPEED_KEY, value=data, updated_at=time.time()))
        else:
            row.value, row.updated_at = data, time.time()
        s.commit()


def expected_output(run):
    if run.task == "translate":
        return max(200, min(run.max_tokens, int(run.prompt_chars / CHARS_PER_TOKEN * 1.1)))
    return min(run.max_tokens, EXPECTED.get(run.task, 400))


def estimate(db, run, now=None):
    now = now or time.time()
    sp = speeds(db, run.model)
    prompt_tokens = run.prompt_chars / CHARS_PER_TOKEN
    read_s = prompt_tokens / sp["read"]
    write_s = expected_output(run) / sp["write"]
    total = max(1.0, read_s + write_s)
    if run.status == "done":
        return 1.0, 0
    if run.status != "running" or not run.started_at:
        return 0.0, int(total)
    if run.phase == "writing" and run.first_token_at:
        share = min(0.99, run.output_tokens / max(1, expected_output(run)))
        done = read_s + share * write_s
    else:
        done = min(read_s * 0.97, now - run.started_at)
    return round(min(0.99, done / total), 4), int(max(0, total - done))


def ahead_of(db, run):
    rows = db.scalars(select(models.FreeAIRun).where(models.FreeAIRun.status.in_(ACTIVE),
                                                     models.FreeAIRun.id != run.id)).all()
    return [r for r in rows if r.status == "running" or (r.task != "minutes" and r.created_at < run.created_at)]


def queued_minutes(db, meeting_id, line_count):
    from .jobs import free_position
    position = free_position(db, meeting_id)
    if not position:
        return None
    rows = db.scalars(select(models.FreeAIRun).where(models.FreeAIRun.status.in_(ACTIVE))).all()
    interactive = [r for r in rows if r.status == "queued" and r.task != "minutes"]
    running = [r for r in rows if r.status == "running"]
    own = models.FreeAIRun(task="minutes", model="", max_tokens=4096, prompt_chars=4000 + 80 * line_count, status="queued")
    wait = sum(estimate(db, r)[1] for r in running + interactive) + estimate(db, own)[1] * max(0, position - 1)
    return {"id": "", "task": "minutes", "label": TASK_LABELS["minutes"], "model": "", "status": "queued", "phase": "queued",
            "progress": 0.0, "eta_seconds": int(wait + estimate(db, own)[1]), "position": position + len(interactive),
            "output_tokens": 0, "updated_at": time.time(), "error": ""}


def payload(db, run, now=None):
    progress, eta = estimate(db, run, now)
    position, wait = 0, 0
    if run.status == "queued":
        ahead = ahead_of(db, run)
        position = len(ahead) + 1
        wait = sum(estimate(db, r, now)[1] for r in ahead)
    return {"id": run.id, "task": run.task, "label": TASK_LABELS.get(run.task, "Working"), "model": name_for(run.model),
            "status": run.status, "phase": run.phase if run.status == "running" else run.status, "progress": progress,
            "eta_seconds": eta + wait, "position": position, "output_tokens": run.output_tokens,
            "updated_at": run.updated_at or run.created_at, "error": run.error[:300] if run.status == "error" else ""}


def ask(db, user, org, task, conn, system, material, max_tokens):
    rid = current_run.get()
    if rid:
        run = db.get(models.FreeAIRun, rid)
        if run is not None and run.user_id == (user.id if user else None) and run.task == task:
            if run.status == "done":
                return run.result
            if run.status == "error":
                message = run.error
                db.delete(run)
                db.commit()
                raise HTTPException(502, "the free AI could not finish: %s" % message[:300])
            raise Pending(payload(db, run))
    busy = db.scalar(select(func.count()).select_from(models.FreeAIRun)
                     .where(models.FreeAIRun.user_id == (user.id if user else None), models.FreeAIRun.status.in_(ACTIVE))) or 0
    if busy >= PER_USER:
        raise HTTPException(429, "the free AI is still working on your earlier requests; wait for them to finish")
    run = models.FreeAIRun(org_id=org.id, user_id=user.id if user else None, task=task, connection_id=conn.id, model=conn.model,
                           system=system, material=material, max_tokens=max_tokens, prompt_chars=len(system) + len(material),
                           updated_at=time.time())
    db.add(run)
    db.commit()
    raise Pending(payload(db, run))


def claim():
    with SessionLocal() as s:
        run = s.scalar(select(models.FreeAIRun).where(models.FreeAIRun.status == "queued", models.FreeAIRun.task != "minutes")
                       .order_by(models.FreeAIRun.created_at).limit(1))
        if run is None:
            return None
        won = s.execute(update(models.FreeAIRun).where(models.FreeAIRun.id == run.id, models.FreeAIRun.status == "queued")
                        .values(status="running", phase="reading", started_at=time.time(), updated_at=time.time()))
        s.commit()
        return run.id if won.rowcount == 1 else None


def tracker(run_id, model):
    state = {"last": 0.0}

    def progress(phase, output=0, stats=None):
        now = time.time()
        if phase == "writing" and now - state["last"] < CHECKPOINT and output > 1:
            return
        state["last"] = now
        with SessionLocal() as s:
            run = s.get(models.FreeAIRun, run_id)
            if run is None:
                return
            if phase == "reading":
                run.phase, run.updated_at = "reading", now
                if output:
                    run.prompt_chars = output
            elif phase == "writing":
                run.phase, run.output_tokens, run.updated_at = "writing", output, now
                run.first_token_at = run.first_token_at or now
            s.commit()
        if phase == "done" and stats:
            learn(model, stats.get("prompt_eval_count") or 0, (stats.get("prompt_eval_duration") or 0) / 1e9,
                  stats.get("eval_count") or 0, (stats.get("eval_duration") or 0) / 1e9)
    return progress


def start_minutes(meeting, conn, org_id, user_id):
    with SessionLocal() as s:
        s.execute(update(models.FreeAIRun).where(models.FreeAIRun.ref == meeting.id, models.FreeAIRun.task == "minutes",
                                                 models.FreeAIRun.status.in_(ACTIVE))
                  .values(status="error", error="replaced", finished_at=time.time()))
        run = models.FreeAIRun(org_id=org_id, user_id=user_id, task="minutes", ref=meeting.id, connection_id=conn.id,
                               model=conn.model, max_tokens=4096, status="running", phase="reading",
                               started_at=time.time(), updated_at=time.time())
        s.add(run)
        s.commit()
        return run.id


def finish(run_id, result="", error=""):
    with SessionLocal() as s:
        run = s.get(models.FreeAIRun, run_id)
        if run is None:
            return
        run.status = "error" if error else "done"
        run.phase = run.status
        run.result, run.error = (result or "")[:200000], (error or "")[:2000]
        run.system, run.material = "", ""
        run.finished_at = run.updated_at = time.time()
        s.commit()


def minutes_progress(db, meeting_id):
    run = db.scalar(select(models.FreeAIRun).where(models.FreeAIRun.ref == meeting_id, models.FreeAIRun.task == "minutes")
                    .order_by(models.FreeAIRun.created_at.desc()).limit(1))
    return payload(db, run) if run is not None and run.status in ACTIVE else None


def cleanup(now=None):
    now = now or time.time()
    with SessionLocal() as s:
        s.execute(delete(models.FreeAIRun).where(models.FreeAIRun.status.in_(("done", "error")), models.FreeAIRun.created_at < now - KEEP))
        s.execute(update(models.FreeAIRun).where(models.FreeAIRun.status.in_(ACTIVE), models.FreeAIRun.created_at < now - 6 * 3600)
                  .values(status="error", error="the free AI took too long; try again", system="", material="", finished_at=now))
        s.commit()


def requeue():
    with SessionLocal() as s:
        s.execute(update(models.FreeAIRun).where(models.FreeAIRun.status == "running", models.FreeAIRun.task != "minutes")
                  .values(status="queued", phase="waiting", output_tokens=0, first_token_at=None))
        s.execute(update(models.FreeAIRun).where(models.FreeAIRun.status == "running", models.FreeAIRun.task == "minutes")
                  .values(status="error", error="restarted", finished_at=time.time()))
        s.commit()
