import os
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from minutes_app import template as tpl_engine

from .. import audit, models, scope, storage
from ..db import get_db
from ..deps import client_ip, current_user, require_role
from .templates import ALLOWED, MAX_UPLOAD, check_docx, safe_name, tpl_payload

router = APIRouter(tags=["template library"])
MAX_LIBRARY = 100


def lib_payload(t, owners):
    return {"id": t.id, "name": t.name, "description": t.description, "filename": t.filename, "mode": t.mode,
            "uses": t.uses, "created_at": t.created_at, "owner_scope": t.owner_scope, "owner": owners.get(t.owner_id, "")}


def owner_for(ctx):
    return ("district", ctx["district"].id) if ctx["scope"] == "district" else ("school", ctx["school"].id)


@router.get("/api/manage/{scope_name}/{target_id}/library")
def scope_library(scope_name: str, target_id: str, user: models.User = Depends(current_user),
                  db: Session = Depends(get_db)):
    ctx = scope.resolve(db, user, scope_name, target_id)
    kind, oid = owner_for(ctx)
    rows = db.scalars(select(models.LibraryTemplate).where(models.LibraryTemplate.owner_scope == kind,
                                                           models.LibraryTemplate.owner_id == oid)
                      .order_by(models.LibraryTemplate.name)).all()
    owners = {ctx["district"].id: ctx["district"].name, **({ctx["school"].id: ctx["school"].name} if ctx["school"] else {})}
    return {"templates": [lib_payload(t, owners) for t in rows]}


@router.post("/api/manage/{scope_name}/{target_id}/library")
async def add_to_library(scope_name: str, target_id: str, request: Request, file: UploadFile = File(...),
                         name: str = Form(""), description: str = Form(""), user: models.User = Depends(current_user),
                         db: Session = Depends(get_db)):
    ctx = scope.resolve(db, user, scope_name, target_id)
    kind, oid = owner_for(ctx)
    count = len(db.scalars(select(models.LibraryTemplate.id).where(models.LibraryTemplate.owner_scope == kind,
                                                                   models.LibraryTemplate.owner_id == oid)).all())
    if count >= MAX_LIBRARY:
        raise HTTPException(400, "a library can hold up to %d templates" % MAX_LIBRARY)
    filename = safe_name(file.filename)
    if not filename.lower().endswith(ALLOWED):
        raise HTTPException(400, "upload a .docx, .pdf, .txt or .md file")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "file is larger than 15 MB")
    if filename.lower().endswith(".docx"):
        check_docx(data)
    work = storage.workdir()
    try:
        src = os.path.join(work, filename)
        with open(src, "wb") as fh:
            fh.write(data)
        try:
            path, mode = tpl_engine.prepare(src, work, "Meeting Minutes", "")
        except Exception as exc:
            raise HTTPException(400, "could not read this file: %s" % exc)
        t = models.LibraryTemplate(owner_scope=kind, owner_id=oid, name=(name or os.path.splitext(filename)[0]).strip()[:200],
                                   description=description.strip()[:1000], filename=filename, storage_key="", mode=mode,
                                   created_by=user.id)
        db.add(t)
        db.flush()
        with open(path, "rb") as fh:
            t.storage_key = storage.store().put("library/%s/%s/%s.docx" % (kind, oid, t.id), fh.read())
        audit.log(db, "library.added", user, ip=client_ip(request), template=t.id, scope=kind, scope_id=oid, name=t.name)
        db.commit()
        return lib_payload(t, {})
    finally:
        shutil.rmtree(work, ignore_errors=True)


@router.delete("/api/manage/{scope_name}/{target_id}/library/{template_id}")
def remove_from_library(scope_name: str, target_id: str, template_id: str, request: Request,
                        user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = scope.resolve(db, user, scope_name, target_id)
    kind, oid = owner_for(ctx)
    t = db.get(models.LibraryTemplate, template_id)
    if t is None or (t.owner_scope, t.owner_id) != (kind, oid):
        raise HTTPException(404, "template not found")
    key = t.storage_key
    audit.log(db, "library.removed", user, ip=client_ip(request), template=t.id, name=t.name)
    db.delete(t)
    db.commit()
    if key:
        storage.store().delete(key)
    return {"ok": True}


def visible(db, org):
    conds = [(models.LibraryTemplate.owner_scope == "district") & (models.LibraryTemplate.owner_id == org.district_id)]
    if org.school_id:
        conds.append((models.LibraryTemplate.owner_scope == "school") & (models.LibraryTemplate.owner_id == org.school_id))
    return db.scalars(select(models.LibraryTemplate).where(or_(*conds)).order_by(models.LibraryTemplate.name)).all()


@router.get("/api/orgs/{org_id}/library")
def org_library(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "member")
    district = db.get(models.District, org.district_id)
    school = db.get(models.School, org.school_id) if org.school_id else None
    owners = {district.id: district.name, **({school.id: school.name} if school else {})}
    return {"templates": [lib_payload(t, owners) for t in visible(db, org)]}


@router.post("/api/orgs/{org_id}/library/{template_id}/use")
def use_template(org_id: str, template_id: str, request: Request, user: models.User = Depends(current_user),
                 db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "secretary")
    t = next((x for x in visible(db, org) if x.id == template_id), None)
    if t is None:
        raise HTTPException(404, "template not found")
    copy = models.Template(org_id=org_id, name=t.name, filename=t.filename, storage_key="", mode=t.mode, created_by=user.id)
    db.add(copy)
    db.flush()
    copy.storage_key = storage.store().put("orgs/%s/templates/%s.docx" % (org_id, copy.id), storage.store().get(t.storage_key))
    t.uses = (t.uses or 0) + 1
    audit.log(db, "library.used", user, org_id, client_ip(request), template=t.id, copy=copy.id)
    db.commit()
    return tpl_payload(copy)
