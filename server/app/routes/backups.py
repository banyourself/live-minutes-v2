from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, backups, governance, models, scope
from ..db import get_db
from ..deps import client_ip, current_user, sudo_user

router = APIRouter(prefix="/api/manage/{scope_name}/{target_id}/backups", tags=["backups"])


class BackupIn(BaseModel):
    name: str
    kind: str
    schedule: str = "weekly"
    data_kinds: list[str] = []
    endpoint: str = ""
    bucket: str = ""
    region: str = ""
    prefix: str = ""
    access_key_id: str = ""
    secret_access_key: str = ""
    container_url: str = ""
    sas_token: str = ""


class BackupPatch(BaseModel):
    name: str | None = None
    schedule: str | None = None
    data_kinds: list[str] | None = None
    active: bool | None = None


def owner(ctx):
    return ("district", ctx["district"].id) if ctx["scope"] == "district" else ("school", ctx["school"].id)


def target_in(db, ctx, backup_id):
    kind, tid = owner(ctx)
    t = db.get(models.BackupTarget, backup_id)
    if t is None or (t.scope, t.target_id) != (kind, tid):
        raise HTTPException(404, "backup destination not found")
    return t


def clean_name(value):
    name = " ".join((value or "").split())[:120]
    if len(name) < 2:
        raise HTTPException(400, "name this destination")
    return name


def check_schedule(value):
    if value not in models.BACKUP_SCHEDULES:
        raise HTTPException(400, "choose daily, weekly, or only when you start it")
    return value


def row(db, t):
    runs = db.scalars(select(models.BackupRun).where(models.BackupRun.backup_id == t.id)
                      .order_by(models.BackupRun.created_at.desc()).limit(8)).all()
    cfg = dict(t.config or {})
    return {"id": t.id, "name": t.name, "kind": t.kind, "schedule": t.schedule, "data_kinds": t.data_kinds or [],
            "active": t.active, "config": cfg, "created_at": t.created_at, "last_run_at": t.last_run_at,
            "runs": [{"id": r.id, "status": r.status, "trigger": r.trigger, "object_key": r.object_key, "size": r.size,
                      "error": r.error, "created_at": r.created_at, "finished_at": r.finished_at} for r in runs]}


@router.get("")
def list_backups(scope_name: str, target_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = scope.resolve(db, user, scope_name, target_id)
    kind, tid = owner(ctx)
    rows = db.scalars(select(models.BackupTarget).where(models.BackupTarget.scope == kind,
                                                        models.BackupTarget.target_id == tid)
                      .order_by(models.BackupTarget.created_at)).all()
    return {"backups": [row(db, t) for t in rows],
            "data_kinds": [{"id": k, "label": v} for k, v in governance.DATA_KINDS.items()]}


@router.post("")
def add_backup(scope_name: str, target_id: str, body: BackupIn, request: Request, user: models.User = Depends(sudo_user),
               db: Session = Depends(get_db)):
    ctx = scope.resolve(db, user, scope_name, target_id)
    kind, tid = owner(ctx)
    count = len(db.scalars(select(models.BackupTarget.id).where(models.BackupTarget.scope == kind,
                                                                models.BackupTarget.target_id == tid)).all())
    if count >= backups.MAX_TARGETS:
        raise HTTPException(400, "you can connect up to %d backup destinations" % backups.MAX_TARGETS)
    config, secret = backups.clean(body.kind, body.model_dump())
    t = models.BackupTarget(scope=kind, target_id=tid, name=clean_name(body.name), kind=body.kind, config=config,
                            secret=secret, data_kinds=backups.clean_kinds(body.data_kinds),
                            schedule=check_schedule(body.schedule), created_by=user.id)
    backups.try_connection(db, t)
    db.add(t)
    audit.log(db, "backup.connected", user, ip=client_ip(request), scope=kind, target=tid, kind=body.kind, name=t.name,
              data=",".join(t.data_kinds), schedule=t.schedule)
    db.commit()
    return row(db, t)


@router.patch("/{backup_id}")
def edit_backup(scope_name: str, target_id: str, backup_id: str, body: BackupPatch, request: Request,
                user: models.User = Depends(sudo_user), db: Session = Depends(get_db)):
    ctx = scope.resolve(db, user, scope_name, target_id)
    t = target_in(db, ctx, backup_id)
    if body.name is not None:
        t.name = clean_name(body.name)
    if body.schedule is not None:
        t.schedule = check_schedule(body.schedule)
    if body.data_kinds is not None:
        t.data_kinds = backups.clean_kinds(body.data_kinds)
    if body.active is not None:
        t.active = body.active
    audit.log(db, "backup.changed", user, ip=client_ip(request), backup=t.id, data=",".join(t.data_kinds),
              schedule=t.schedule, active=t.active)
    db.commit()
    return row(db, t)


@router.delete("/{backup_id}")
def remove_backup(scope_name: str, target_id: str, backup_id: str, request: Request,
                  user: models.User = Depends(sudo_user), db: Session = Depends(get_db)):
    ctx = scope.resolve(db, user, scope_name, target_id)
    t = target_in(db, ctx, backup_id)
    audit.log(db, "backup.disconnected", user, ip=client_ip(request), backup=t.id, name=t.name)
    db.delete(t)
    db.commit()
    return {"ok": True}


@router.post("/{backup_id}/test")
def test_backup(scope_name: str, target_id: str, backup_id: str, user: models.User = Depends(sudo_user),
                db: Session = Depends(get_db)):
    ctx = scope.resolve(db, user, scope_name, target_id)
    return {"ok": True, "wrote": backups.try_connection(db, target_in(db, ctx, backup_id))}


@router.post("/{backup_id}/run")
def run_backup(scope_name: str, target_id: str, backup_id: str, request: Request, user: models.User = Depends(sudo_user),
               db: Session = Depends(get_db)):
    ctx = scope.resolve(db, user, scope_name, target_id)
    t = target_in(db, ctx, backup_id)
    busy = db.scalar(select(models.BackupRun.id).where(models.BackupRun.backup_id == t.id,
                                                       models.BackupRun.status.in_(("queued", "running"))))
    if busy:
        raise HTTPException(409, "a backup to this destination is already running")
    db.add(models.BackupRun(backup_id=t.id, trigger="manual", requested_by=user.id))
    audit.log(db, "backup.requested", user, ip=client_ip(request), backup=t.id)
    db.commit()
    return row(db, t)
