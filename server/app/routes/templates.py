import io
import json
import os
import re
import shutil
import zipfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from minutes_app import drafter, template as tpl_engine

from .. import audit, models, ratelimit, storage
from ..db import get_db
from ..deps import client_ip, current_user, require_role

router = APIRouter(tags=["templates"])
ALLOWED = (".docx", ".pdf", ".txt", ".md")
MAX_UPLOAD = 15 * 1024 * 1024
MAX_UNPACKED = 60 * 1024 * 1024
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TYPES = {".docx": DOCX, ".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8"}


class DesignIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str = ""
    title: str = ""
    topics: list[str] = []
    attendance: bool = True
    action_items: bool = True
    summary: bool = True
    style: dict = {}
    source: str = ""


def check_docx(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
    except zipfile.BadZipFile:
        raise HTTPException(400, "this .docx file is damaged or not a Word document")
    if len(infos) > 2000 or sum(i.file_size for i in infos) > MAX_UNPACKED:
        raise HTTPException(400, "this .docx file is too large once unpacked")


def safe_name(name):
    return re.sub(r"[^\w.\- ]+", "_", os.path.basename(name or "upload"))[:120] or "upload"


def tpl_payload(t):
    return {"id": t.id, "name": t.name, "filename": t.filename, "mode": t.mode, "created_at": t.created_at,
            "purpose": t.purpose or "template", "editable": t.mode == "generated" and (t.purpose or "template") == "template"}


def clean_design(body, fallback_title):
    raw = body.model_dump()
    if len(raw.get("topics") or []) > 60:
        raise HTTPException(400, "a template can have up to 60 topics")
    if len(json.dumps(raw, default=str)) > 30_000:
        raise HTTPException(400, "this template is too large")
    if not (raw.get("title") or "").strip():
        raw["title"] = fallback_title
    design = tpl_engine.normalize(raw)
    if not design["topics"]:
        raise HTTPException(400, "add at least one agenda topic")
    design["name"] = " ".join((raw.get("name") or "").split())[:200] or "Custom template"
    return design


def stored_design(t, fallback_title, topics=None):
    raw = dict(t.design or {"title": fallback_title, "topics": topics or []})
    design = tpl_engine.normalize(raw)
    design["name"] = t.name
    return design


def build_docx(design, work):
    path = os.path.join(work, "template.docx")
    tpl_engine.generate(design["topics"], path, design=design)
    with open(path, "rb") as fh:
        return fh.read()


def download_name(name, ext):
    return (re.sub(r"[^A-Za-z0-9 _-]+", "", name).strip()[:80] or "template") + ext


def save_generated(t, design, work):
    t.storage_key = storage.store().put("orgs/%s/templates/%s.docx" % (t.org_id, t.id), build_docx(design, work))


@router.get("/api/orgs/{org_id}/templates")
def list_templates(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, org_id, "member")
    rows = db.scalars(select(models.Template).where(models.Template.org_id == org_id)
                      .order_by(models.Template.created_at.desc())).all()
    return {"templates": [tpl_payload(t) for t in rows]}


@router.post("/api/orgs/{org_id}/templates")
async def upload_template(org_id: str, request: Request, file: UploadFile = File(...), name: str = Form(""),
                          title: str = Form(""), date: str = Form(""), purpose: str = Form("template"),
                          user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, org_id, "secretary")
    if purpose not in ("template", "example"):
        raise HTTPException(400, "choose a template or an example")
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
        example = ""
        try:
            if purpose == "example":
                example = tpl_engine.read_text(src)
                if len(example) < 40:
                    raise ValueError("there is not enough text in it to learn a style from")
                path, mode = src, "example"
            else:
                path, mode = tpl_engine.prepare(src, work, title or "Meeting Minutes", date)
        except Exception as exc:
            raise HTTPException(400, "could not read this file: %s" % exc)
        t = models.Template(org_id=org_id, name=(name or os.path.splitext(filename)[0])[:200], filename=filename,
                            storage_key="", mode=mode, purpose=purpose, example_text=example, created_by=user.id)
        db.add(t)
        db.flush()
        ext = os.path.splitext(path)[1].lower() or ".docx"
        with open(path, "rb") as fh:
            t.storage_key = storage.store().put("orgs/%s/templates/%s%s" % (org_id, t.id, ext), fh.read())
        audit.log(db, "template.uploaded", user, org_id, client_ip(request), template=t.id, mode=mode, purpose=purpose)
        db.commit()
        return tpl_payload(t)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def template_for(db, user, template_id, minimum="member"):
    t = db.get(models.Template, template_id)
    if t is None:
        raise HTTPException(404, "template not found")
    require_role(db, user, t.org_id, minimum)
    return t


@router.get("/api/templates/{template_id}/outline")
def outline(template_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    t = template_for(db, user, template_id)
    if t.purpose == "example":
        return {"template": tpl_payload(t), "outline": None, "example": t.example_text[:4000]}
    work = storage.workdir()
    try:
        return {"template": tpl_payload(t), "outline": drafter.template_outline(storage.store().local_copy(t.storage_key, work))}
    finally:
        shutil.rmtree(work, ignore_errors=True)


@router.get("/api/templates/builtin")
def builtin(user: models.User = Depends(current_user)):
    return {"templates": [{"key": k, "name": v["name"], "description": v["description"],
                           "topics": tpl_engine.clean_topics(v["topics"]),
                           "design": dict(tpl_engine.preset(k, "Meeting Minutes"), name=v["name"])}
                          for k, v in tpl_engine.BUILTIN.items()],
            "options": {"fonts": list(tpl_engine.FONTS)}}


@router.post("/api/templates/preview")
def preview(body: DesignIn, user: models.User = Depends(current_user)):
    ratelimit.hit("tpl-preview:" + user.id, 60, 600)
    design = clean_design(body, "Meeting Minutes")
    work = storage.workdir()
    try:
        data = build_docx(design, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return Response(data, media_type=DOCX, headers={
        "Content-Disposition": 'attachment; filename="%s"' % download_name(design["name"], ".docx")})


@router.post("/api/orgs/{org_id}/templates/design")
def create_designed(org_id: str, body: DesignIn, request: Request, user: models.User = Depends(current_user),
                    db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "secretary")
    design = clean_design(body, org.name + " Minutes")
    work = storage.workdir()
    try:
        t = models.Template(org_id=org_id, name=design["name"], filename=download_name(design["name"], ".docx"),
                            storage_key="", mode="generated", purpose="template", design=design, created_by=user.id)
        db.add(t)
        db.flush()
        save_generated(t, design, work)
        cfg = dict(org.settings or {})
        if not cfg.get("default_template_id"):
            cfg["default_template_id"] = t.id
            org.settings = cfg
        audit.log(db, "template.designed", user, org_id, client_ip(request), template=t.id,
                  source=body.source if body.source in tpl_engine.BUILTIN else "custom", topics=len(design["topics"]))
        db.commit()
        return tpl_payload(t)
    finally:
        shutil.rmtree(work, ignore_errors=True)


@router.get("/api/templates/{template_id}/design")
def get_design(template_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    t = template_for(db, user, template_id)
    if not tpl_payload(t)["editable"]:
        raise HTTPException(400, "only templates made from topics can be edited here; edit your own file in Word and upload it again")
    org = db.get(models.Organization, t.org_id)
    if t.design:
        return {"template": tpl_payload(t), "design": stored_design(t, org.name + " Minutes")}
    work = storage.workdir()
    try:
        slots = drafter.template_outline(storage.store().local_copy(t.storage_key, work))["slots"]
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {"template": tpl_payload(t), "design": stored_design(t, org.name + " Minutes", slots)}


@router.put("/api/templates/{template_id}/design")
def update_design(template_id: str, body: DesignIn, request: Request, user: models.User = Depends(current_user),
                  db: Session = Depends(get_db)):
    t = template_for(db, user, template_id, "secretary")
    if not tpl_payload(t)["editable"]:
        raise HTTPException(400, "only templates made from topics can be edited here")
    org = db.get(models.Organization, t.org_id)
    design = clean_design(body, org.name + " Minutes")
    work = storage.workdir()
    try:
        old_key = t.storage_key
        save_generated(t, design, work)
        if old_key and old_key != t.storage_key:
            storage.store().delete(old_key)
        t.name, t.design = design["name"], design
        audit.log(db, "template.edited", user, t.org_id, client_ip(request), template=t.id, topics=len(design["topics"]))
        db.commit()
        return tpl_payload(t)
    finally:
        shutil.rmtree(work, ignore_errors=True)


@router.get("/api/templates/{template_id}/file")
def template_file(template_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    t = template_for(db, user, template_id)
    ext = os.path.splitext(t.storage_key)[1].lower() or ".docx"
    return Response(storage.store().get(t.storage_key), media_type=TYPES.get(ext, "application/octet-stream"),
                    headers={"Content-Disposition": 'attachment; filename="%s"' % download_name(t.name, ext)})


@router.post("/api/orgs/{org_id}/templates/builtin/{key}")
def use_builtin(org_id: str, key: str, request: Request, user: models.User = Depends(current_user),
                db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "secretary")
    if key not in tpl_engine.BUILTIN:
        raise HTTPException(404, "template not found")
    name = tpl_engine.BUILTIN[key]["name"]
    work = storage.workdir()
    try:
        design = dict(tpl_engine.preset(key, org.name + " Minutes"), name=name)
        t = models.Template(org_id=org_id, name=name, filename=key + ".docx", storage_key="", mode="generated",
                            purpose="template", design=design, created_by=user.id)
        db.add(t)
        db.flush()
        save_generated(t, design, work)
        cfg = dict(org.settings or {})
        if not cfg.get("default_template_id"):
            cfg["default_template_id"] = t.id
            org.settings = cfg
        audit.log(db, "template.builtin", user, org_id, client_ip(request), template=t.id, key=key)
        db.commit()
        return tpl_payload(t)
    finally:
        shutil.rmtree(work, ignore_errors=True)


@router.delete("/api/templates/{template_id}")
def delete_template(template_id: str, request: Request, user: models.User = Depends(current_user),
                    db: Session = Depends(get_db)):
    t = template_for(db, user, template_id, "secretary")
    in_use = db.scalar(select(models.Meeting).where(models.Meeting.template_id == t.id).limit(1))
    if in_use is not None:
        raise HTTPException(400, "this template is used by a meeting; delete those meetings first")
    key = t.storage_key
    org = db.get(models.Organization, t.org_id)
    cfg = dict(org.settings or {})
    for field in ("default_template_id", "example_template_id"):
        if cfg.get(field) == t.id:
            cfg[field] = ""
    org.settings = cfg
    db.delete(t)
    audit.log(db, "template.deleted", user, t.org_id, client_ip(request), template=t.id)
    db.commit()
    if key:
        storage.store().delete(key)
    return {"ok": True}
