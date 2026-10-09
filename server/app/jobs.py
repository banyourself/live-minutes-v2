import json
import os
import shutil
import threading
import time
import traceback
import urllib.request

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.orm import aliased

from minutes_app import drafter, llm

from . import (ai_runtime, backups, free_ai, governance, history, media, mailer, models, notify, offsite, officers,
               ratelimit, references, runtime, scheduling, storage)
from .db import SessionLocal
from .live import line_count, transcript_for
from .settings import settings

ACTIVE = ("queued", "running")
MAX_ATTEMPTS = 3
FREE_STALE = 4 * 3600
MAINTAIN_EVERY = 60
SCHEDULE_EVERY = 600
DIGEST_EVERY = 3600
PURGE_EVERY = 6 * 3600
_last_maintain = [0.0]
_last_purge = [0.0]
_last_schedule = [0.0]
_last_digest = [0.0]


class Superseded(Exception):
    pass


def enqueue(db, meeting, kind="update"):
    pending = db.scalar(select(models.Job).where(models.Job.meeting_id == meeting.id,
                                                 models.Job.status == "queued"))
    if pending is not None:
        if kind == "full":
            pending.kind = "full"
        pending.run_after = 0.0
        return pending
    job = models.Job(meeting_id=meeting.id, kind=kind, run_after=0.0)
    db.add(job)
    meeting.draft_status = "queued"
    meeting.draft_error = ""
    return job


def maybe_enqueue_live(db, meeting):
    if meeting.run_mode != "live" or meeting.status != "open" or not meeting.ai_connection_id:
        return None
    if meeting.ai_connection_id in ai_runtime.free_ids(db):
        return None
    new = line_count(db, meeting.id) - meeting.drafted_upto
    last = meeting.drafted_at or meeting.created_at
    due = new >= int(runtime.get("live_lines")) or (new > 0 and time.time() - last >= int(runtime.get("live_seconds")))
    return enqueue(db, meeting) if due else None


def free_meetings(free_ids):
    return select(models.Meeting.id).where(models.Meeting.ai_connection_id.in_(free_ids))


def in_lane(stmt, lane, free_ids):
    if lane == "free":
        return stmt.where(models.Job.meeting_id.in_(free_meetings(free_ids)))
    return stmt.where(models.Job.meeting_id.not_in(free_meetings(free_ids))) if free_ids else stmt


def claim(db, lane="main"):
    free_id = ai_runtime.free_ids(db)
    if lane == "free" and not free_id:
        db.rollback()
        return None
    other = aliased(models.Job)
    busy = exists().where(other.meeting_id == models.Job.meeting_id, other.status == "running")
    stmt = in_lane(select(models.Job).where(models.Job.status == "queued", models.Job.run_after <= time.time(), ~busy),
                   lane, free_id).order_by(models.Job.created_at).limit(1)
    if db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True, of=models.Job)
    job = db.scalar(stmt)
    if job is None:
        db.rollback()
        return None
    won = db.execute(update(models.Job).where(models.Job.id == job.id, models.Job.status == "queued")
                     .values(status="running", started_at=time.time(), attempts=models.Job.attempts + 1))
    db.commit()
    return db.get(models.Job, job.id) if won.rowcount == 1 else False


def roster_notes(org, meeting):
    cfg = org.settings or {}
    parts = [meeting.notes or ""]
    aliases = cfg.get("aliases") or []
    if aliases:
        parts.append("Name aliases (caption name -> real name): " +
                     "; ".join("%s -> %s" % (a.get("from", ""), a.get("to", "")) for a in aliases))
    shared = cfg.get("shared_accounts") or []
    if shared:
        parts.append("SHARED ACCOUNTS (several people speak from each; tell them apart from context): " +
                     "; ".join("%s (%s)" % (s.get("name", ""), ", ".join(s.get("people") or []) or "people not listed")
                               for s in shared))
    return "\n".join(p for p in parts if p.strip())


def _finish_superseded(db, job_id):
    db.rollback()
    job = db.get(models.Job, job_id)
    if job is not None:
        job.status, job.finished_at = "done", time.time()
        meeting = db.get(models.Meeting, job.meeting_id)
        if meeting is not None:
            meeting.draft_status = "idle"
        db.commit()


def _finish_failed(db, job_id, exc):
    db.rollback()
    job = db.get(models.Job, job_id)
    if job is None:
        return
    meeting = db.get(models.Meeting, job.meeting_id)
    message = str(exc)[:2000]
    if job.attempts < MAX_ATTEMPTS:
        job.status, job.error = "queued", message
        job.run_after = time.time() + 20 * (3 ** max(0, job.attempts - 1))
        if meeting is not None:
            meeting.draft_status, meeting.draft_error = "queued", "retrying: " + message[:300]
    else:
        job.status, job.error, job.finished_at = "error", message, time.time()
        if meeting is not None:
            meeting.draft_status, meeting.draft_error = "error", message
            if job.kind == "full":
                notify.draft_ready(db, meeting, ok=False, error=message)
    db.commit()


def example_for(db, org):
    chosen = (org.settings or {}).get("example_template_id")
    tpl = db.get(models.Template, chosen) if chosen else None
    if tpl is None or tpl.org_id != org.id or tpl.purpose != "example":
        tpl = db.scalar(select(models.Template).where(models.Template.org_id == org.id, models.Template.purpose == "example")
                        .order_by(models.Template.created_at.desc()).limit(1))
    return tpl.example_text if tpl is not None else ""


def hand_off(db, job, meeting):
    job.status, job.attempts = "queued", max(0, (job.attempts or 1) - 1)
    meeting.draft_status = "queued"
    db.commit()


def free_position(db, meeting_id):
    free_id = ai_runtime.free_ids(db)
    mine = db.scalar(select(models.Job).where(models.Job.meeting_id == meeting_id, models.Job.status.in_(ACTIVE))
                     .order_by(models.Job.created_at).limit(1))
    if not free_id or mine is None:
        return 0
    if mine.status == "running":
        return 1
    ahead = db.scalar(select(func.count()).select_from(models.Job)
                      .where(models.Job.status.in_(ACTIVE), models.Job.meeting_id.in_(free_meetings(free_id)),
                             or_(models.Job.status == "running", models.Job.created_at < mine.created_at))) or 0
    return int(ahead) + 1


def run(job_id, lane="main"):
    db = SessionLocal()
    free_run = None
    work = storage.workdir()
    try:
        job = db.get(models.Job, job_id)
        meeting = db.get(models.Meeting, job.meeting_id)
        if meeting.status == "approved":
            raise Superseded()
        org = db.get(models.Organization, meeting.org_id)
        tpl = db.get(models.Template, meeting.template_id)
        conn = db.get(models.AIConnection, meeting.ai_connection_id) if meeting.ai_connection_id else None
        if conn is None:
            conn, _ = ai_runtime.resolve_connection(db, db.get(models.User, meeting.created_by), org, "minutes")
            if conn is None:
                raise RuntimeError("no AI is set up for drafting minutes; add one under Settings, AI")
            meeting.ai_connection_id = conn.id
        if ai_runtime.is_free(conn) and not ai_runtime.free_enabled():
            raise RuntimeError("the free AI is turned off on this server; choose another AI for this meeting")
        if ai_runtime.is_free(conn) != (lane == "free"):
            hand_off(db, job, meeting)
            return
        if not ai_runtime.usable_for_org(db, conn, org, db.get(models.User, meeting.created_by)):
            raise RuntimeError("the AI chosen for this meeting is no longer shared with %s; choose another one" % org.name)
        limit = ai_runtime.over_limit(db, org)
        if limit:
            raise RuntimeError(limit)
        start_rev = meeting.draft_rev or 0
        meeting.draft_status = "drafting"
        db.commit()
        tr, rows = transcript_for(db, meeting.id)
        upto = len(rows)
        full = job.kind == "full" or not meeting.draft
        text = tr.text() if full else tr.text(max(0, meeting.drafted_upto - 15))
        template_path = storage.store().local_copy(tpl.storage_key, work)
        creds = ai_runtime.creds_for(conn, org.id, meeting.created_by, "minutes")
        if lane == "free":
            free_run = free_ai.start_minutes(meeting, conn, org.id, meeting.created_by)
            creds["progress"] = free_ai.tracker(free_run, conn.model)
        task_prompt, _ = ai_runtime.resolve_prompt(db, org, "minutes")
        data, bad = drafter.draft(conn.provider, conn.model, template_path, text,
                                  meeting.draft or None, roster_notes(org, meeting),
                                  generated=(tpl.mode == "generated"), creds=creds,
                                  style_rules=(org.settings or {}).get("style_rules") or None,
                                  instructions=ai_runtime.context_for(db, org) + "\n\n" + task_prompt, example=example_for(db, org),
                                  reference=references.for_prompt(db, meeting.id))
        db.refresh(meeting)
        if meeting.status == "approved":
            raise Superseded()
        if (meeting.draft_rev or 0) != start_rev:
            job.status, job.finished_at = "done", time.time()
            meeting.draft_status = "idle"
            db.flush()
            enqueue(db, meeting, "full" if job.kind == "full" else "update")
            db.commit()
            if free_run:
                free_ai.finish(free_run, error="superseded")
            return
        before = meeting.draft or {}
        meeting.draft, meeting.problems = data, bad
        meeting.draft_rev = start_rev + 1
        history.record(db, meeting, before, "ai", None, conn.label)
        meeting.drafted_upto, meeting.drafted_at = upto, time.time()
        meeting.draft_status, meeting.draft_error = "idle", ""
        job.status, job.finished_at = "done", time.time()
        if (job.kind == "full" or lane == "free") and meeting.status == "ended":
            notify.draft_ready(db, meeting)
        db.commit()
        if free_run:
            free_ai.finish(free_run)
    except Superseded:
        if free_run:
            free_ai.finish(free_run, error="superseded")
        _finish_superseded(db, job_id)
    except Exception as exc:
        if free_run:
            free_ai.finish(free_run, error=str(exc))
        _finish_failed(db, job_id, exc)
        if os.environ.get("LIVE_MINUTES_DEBUG"):
            traceback.print_exc()
    finally:
        db.close()
        shutil.rmtree(work, ignore_errors=True)


def run_once(lane="main"):
    db = SessionLocal()
    try:
        job = claim(db, lane)
    finally:
        db.close()
    if job is False:
        return True
    if job is None:
        return False
    run(job.id, lane)
    return True


def recover_stale(max_age=900, free_age=FREE_STALE):
    db = SessionLocal()
    try:
        free_id = ai_runtime.free_ids(db)
        stale = update(models.Job).where(models.Job.status == "running").values(status="queued", run_after=0.0)
        if free_id:
            db.execute(stale.where(models.Job.started_at < time.time() - max_age,
                                   models.Job.meeting_id.not_in(free_meetings(free_id))))
            db.execute(stale.where(models.Job.started_at < time.time() - free_age,
                                   models.Job.meeting_id.in_(free_meetings(free_id))))
        else:
            db.execute(stale.where(models.Job.started_at < time.time() - max_age))
        db.commit()
    finally:
        db.close()


def pull_free_model():
    for model in settings.free_ai_models:
        body = json.dumps({"model": model, "stream": False}).encode()
        req = urllib.request.Request(settings.free_ai_url + "/api/pull", data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=3600) as resp:
                resp.read()
        except Exception as exc:
            print("free AI model pull failed for %s: %s" % (model, exc), flush=True)
            return False
    return True


def requeue_free():
    db = SessionLocal()
    try:
        free_id = ai_runtime.free_ids(db)
        if free_id:
            db.execute(update(models.Job).where(models.Job.status == "running",
                                                models.Job.meeting_id.in_(free_meetings(free_id)))
                       .values(status="queued", run_after=0.0))
            db.commit()
    finally:
        db.close()


JSON_TASKS = ("minutes", "translate", "assistant")


def run_free_request():
    run_id = free_ai.claim()
    if not run_id:
        return False
    with SessionLocal() as s:
        run = s.get(models.FreeAIRun, run_id)
        conn = s.get(models.AIConnection, run.connection_id)
        if conn is None or not ai_runtime.usable_for_org(s, conn, None):
            free_ai.finish(run_id, error="this free AI is no longer available; choose another AI")
            return True
        creds = ai_runtime.creds_for(conn, run.org_id, run.user_id, run.task)
        creds["progress"] = free_ai.tracker(run_id, run.model)
        creds["json"] = run.task in JSON_TASKS
        args = (run.model, run.system, run.material, run.max_tokens)
    try:
        text = llm.complete("builtin", args[0], args[1], args[2], max_tokens=args[3], creds=creds)
        free_ai.finish(run_id, result=text)
    except Exception as exc:
        free_ai.finish(run_id, error=str(exc))
    return True


def free_loop(stop=None, idle=5.0):
    ai_runtime.ensure_free_conn()
    while not pull_free_model():
        if stop and stop.wait(60):
            return
        if not stop:
            time.sleep(60)
    requeue_free()
    free_ai.requeue()
    while not (stop and stop.is_set()):
        try:
            if not (run_free_request() or run_once("free")):
                time.sleep(idle)
        except Exception:
            traceback.print_exc()
            time.sleep(idle)


def maintain(force=False):
    now = time.time()
    if not force and now - _last_maintain[0] < MAINTAIN_EVERY:
        return
    _last_maintain[0] = now
    recover_stale()
    free_ai.cleanup()
    ratelimit.purge()
    runtime.heartbeat()
    db = SessionLocal()
    try:
        db.execute(delete(models.UserSession).where(models.UserSession.expires_at < now))
        db.execute(delete(models.EmailToken).where(models.EmailToken.expires_at < now - 86400))
        db.execute(delete(models.OAuthCode).where(models.OAuthCode.expires_at < now - 86400))
        db.execute(delete(models.PersonalToken).where(models.PersonalToken.client_id.is_not(None),
                                                      models.PersonalToken.refresh_expires_at < now))
        db.execute(delete(models.OAuthClient).where(models.OAuthClient.last_used_at.is_(None),
                                                    models.OAuthClient.created_at < now - 7 * 86400))
        db.execute(delete(models.OutboxEmail).where(models.OutboxEmail.sent_at.is_not(None),
                                                    models.OutboxEmail.sent_at < now - 7 * 86400))
        officers.expire(db, now)
        if force or now - _last_schedule[0] >= SCHEDULE_EVERY:
            _last_schedule[0] = now
            scheduling.materialize_all(db, now)
        notify.remind(db, now)
        if force or now - _last_digest[0] >= DIGEST_EVERY:
            _last_digest[0] = now
            notify.digests(db, now)
            notify.purge(db, now)
            media.cleanup()
        if now - _last_purge[0] >= PURGE_EVERY:
            _last_purge[0] = now
            governance.purge(db, now)
        backups.schedule_due(db, now)
        offsite.run_due(db, now)
        db.commit()
    finally:
        db.close()


def loop(stop=None, idle=1.0):
    if ai_runtime.free_enabled():
        threading.Thread(target=free_loop, args=(stop,), daemon=True, name="live-minutes-free-ai").start()
    maintain(force=True)
    while not (stop and stop.is_set()):
        try:
            maintain()
            mailer.deliver_pending()
            if not run_once() and not governance.run_exports() and not backups.run_backups():
                time.sleep(idle)
        except Exception:
            traceback.print_exc()
            time.sleep(idle)


def start_inline():
    stop = threading.Event()
    threading.Thread(target=loop, args=(stop,), daemon=True, name="live-minutes-worker").start()
    return stop
