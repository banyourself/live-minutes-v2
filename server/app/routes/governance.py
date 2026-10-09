import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, governance, models, scope, storage
from ..db import get_db
from ..deps import client_ip, current_user, sudo_user

router = APIRouter(prefix="/api/manage/{scope_name}/{target_id}", tags=["records management"])


class RetentionIn(BaseModel):
    unapproved_days: int = 0
    transcript_days: int = 0
    approved_years: int = 0


class HoldIn(BaseModel):
    scope: str
    target_id: str
    reason: str


def district_only(ctx, what):
    if ctx["scope"] != "district":
        raise HTTPException(403, "%s is set by district IT for the whole district" % what)


def in_district(db, ctx, scope_name, target_id):
    d = ctx["district"]
    if scope_name == "district":
        return d.name if target_id == d.id else None
    if scope_name == "school":
        s = db.get(models.School, target_id)
        return s.name if s is not None and s.district_id == d.id else None
    if scope_name == "org":
        o = db.get(models.Organization, target_id)
        return o.name if o is not None and o.district_id == d.id else None
    return None


def visible_to(ctx, h, db):
    if ctx["scope"] == "district":
        return True
    school = ctx["school"]
    if h.scope == "district":
        return True
    if h.scope == "school":
        return h.target_id == school.id
    o = db.get(models.Organization, h.target_id)
    return o is not None and o.school_id == school.id


def hold_row(db, ctx, h):
    people = db.get(models.User, h.created_by)
    return {"id": h.id, "scope": h.scope, "target_id": h.target_id, "target": in_district(db, ctx, h.scope, h.target_id) or "",
            "reason": h.reason, "created_at": h.created_at, "created_by": people.email if people else "",
            "released_at": h.released_at}


@router.get("/retention")
def get_retention(scope_name: str, target_id: str, user: models.User = Depends(current_user),
                  db: Session = Depends(get_db)):
    ctx = scope.resolve(db, user, scope_name, target_id)
    d = ctx["district"]
    return {"retention": governance.retention(d), "preview": governance.preview(db, d),
            "editable": ctx["scope"] == "district", "limits": governance.LIMITS}


@router.put("/retention")
def put_retention(scope_name: str, target_id: str, body: RetentionIn, request: Request,
                  user: models.User = Depends(sudo_user), db: Session = Depends(get_db)):
    ctx = scope.resolve(db, user, scope_name, target_id)
    district_only(ctx, "Retention")
    cfg = governance.clean_retention(body.model_dump())
    d = ctx["district"]
    d.settings = dict(d.settings or {}, retention=cfg)
    audit.log(db, "retention.set", user, ip=client_ip(request), district=d.id, **cfg)
    db.commit()
    return {"retention": cfg, "preview": governance.preview(db, d), "editable": True, "limits": governance.LIMITS}


@router.get("/holds")
def holds(scope_name: str, target_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = scope.resolve(db, user, scope_name, target_id)
    rows = db.scalars(select(models.LegalHold).where(models.LegalHold.district_id == ctx["district"].id)
                      .order_by(models.LegalHold.created_at.desc())).all()
    return {"holds": [hold_row(db, ctx, h) for h in rows if visible_to(ctx, h, db)],
            "can_manage": ctx["scope"] == "district"}


@router.post("/holds")
def add_hold(scope_name: str, target_id: str, body: HoldIn, request: Request, user: models.User = Depends(sudo_user),
             db: Session = Depends(get_db)):
    ctx = scope.resolve(db, user, scope_name, target_id)
    district_only(ctx, "A legal hold")
    if body.scope not in models.HOLD_SCOPES:
        raise HTTPException(400, "a hold covers the district, a college, or an organization")
    name = in_district(db, ctx, body.scope, body.target_id)
    if name is None:
        raise HTTPException(404, "that is not part of this district")
    reason = " ".join((body.reason or "").split())[:1000]
    if len(reason) < 3:
        raise HTTPException(400, "say why the records are on hold, such as a case or request number")
    h = models.LegalHold(district_id=ctx["district"].id, scope=body.scope, target_id=body.target_id, reason=reason,
                         created_by=user.id)
    db.add(h)
    audit.log(db, "hold.placed", user, ip=client_ip(request), scope=body.scope, target=body.target_id, name=name, reason=reason)
    db.commit()
    return hold_row(db, ctx, h)


@router.post("/holds/{hold_id}/release")
def release_hold(scope_name: str, target_id: str, hold_id: str, request: Request, user: models.User = Depends(sudo_user),
                 db: Session = Depends(get_db)):
    ctx = scope.resolve(db, user, scope_name, target_id)
    district_only(ctx, "A legal hold")
    h = db.get(models.LegalHold, hold_id)
    if h is None or h.district_id != ctx["district"].id:
        raise HTTPException(404, "hold not found")
    if h.released_at is None:
        h.released_at, h.released_by = time.time(), user.id
        audit.log(db, "hold.released", user, ip=client_ip(request), scope=h.scope, target=h.target_id)
        db.commit()
    return hold_row(db, ctx, h)


def export_row(j):
    return {"id": j.id, "status": j.status, "size": j.size, "counts": j.counts or {}, "error": j.error,
            "created_at": j.created_at, "finished_at": j.finished_at, "expires_at": j.expires_at}


def scope_key(ctx):
    return ("district", ctx["district"].id) if ctx["scope"] == "district" else ("school", ctx["school"].id)


@router.get("/exports")
def exports(scope_name: str, target_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = scope.resolve(db, user, scope_name, target_id)
    kind, tid = scope_key(ctx)
    rows = db.scalars(select(models.ExportJob).where(models.ExportJob.scope == kind, models.ExportJob.target_id == tid)
                      .order_by(models.ExportJob.created_at.desc()).limit(20)).all()
    return {"exports": [export_row(j) for j in rows]}


@router.post("/exports")
def request_export(scope_name: str, target_id: str, request: Request, user: models.User = Depends(sudo_user),
                   db: Session = Depends(get_db)):
    ctx = scope.resolve(db, user, scope_name, target_id)
    kind, tid = scope_key(ctx)
    busy = db.scalars(select(models.ExportJob.id).where(models.ExportJob.scope == kind, models.ExportJob.target_id == tid,
                                                        models.ExportJob.status.in_(("queued", "running")))).all()
    if busy:
        raise HTTPException(409, "an export is already being prepared")
    j = models.ExportJob(scope=kind, target_id=tid, requested_by=user.id)
    db.add(j)
    audit.log(db, "export.requested", user, ip=client_ip(request), scope=kind, target=tid)
    db.commit()
    return export_row(j)


@router.get("/exports/{export_id}/download")
def download_export(scope_name: str, target_id: str, export_id: str, request: Request, check: int = 0,
                    user: models.User = Depends(sudo_user), db: Session = Depends(get_db)):
    ctx = scope.resolve(db, user, scope_name, target_id)
    kind, tid = scope_key(ctx)
    j = db.get(models.ExportJob, export_id)
    if j is None or (j.scope, j.target_id) != (kind, tid):
        raise HTTPException(404, "export not found")
    if j.status != "done" or not j.storage_key:
        raise HTTPException(409, "this export is not ready or has expired")
    if check:
        return {"ready": True}
    audit.log(db, "export.downloaded", user, ip=client_ip(request), export=j.id, scope=kind, target=tid)
    db.commit()
    name = governance.slug(ctx["district"].name if kind == "district" else ctx["school"].name, "export")
    return Response(storage.store().get(j.storage_key), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="live-minutes-%s-%s.zip"' % (
                        name, time.strftime("%Y-%m-%d", time.gmtime(j.finished_at or time.time()))),
                             "Cache-Control": "no-store"})
