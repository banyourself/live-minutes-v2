import os
import shutil

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from minutes_app import accessibility, drafter

from .. import models, ratelimit, storage
from ..db import get_db
from ..deps import client_ip

router = APIRouter(tags=["public archive"])
LIMIT = 200
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def public_org(db, org_id):
    org = db.get(models.Organization, (org_id or "")[:32])
    if org is None or not (org.settings or {}).get("public_archive"):
        raise HTTPException(404, "not found")
    return org


@router.get("/api/public/orgs/{org_id}")
def archive(org_id: str, request: Request, db: Session = Depends(get_db)):
    ratelimit.hit("public-archive:" + client_ip(request), 120, 600)
    org = public_org(db, org_id)
    rows = db.scalars(select(models.Meeting)
                      .where(models.Meeting.org_id == org.id, models.Meeting.status == "approved", models.Meeting.sample.is_(False))
                      .order_by(models.Meeting.approved_at.desc()).limit(LIMIT)).all()
    return {"name": org.name, "school": org.school,
            "meetings": [{"id": m.id, "title": m.title, "meeting_date": m.meeting_date, "approved_at": m.approved_at,
                          "summary": (m.plain_summary or "")[:4000]} for m in rows]}


@router.get("/api/public/meetings/{meeting_id}/minutes.docx")
def approved_minutes(meeting_id: str, request: Request, db: Session = Depends(get_db)):
    ratelimit.hit("public-minutes:" + client_ip(request), 30, 600)
    mt = db.get(models.Meeting, (meeting_id or "")[:32])
    if mt is None or mt.status != "approved" or mt.sample:
        raise HTTPException(404, "not found")
    org = public_org(db, mt.org_id)
    tpl = db.get(models.Template, mt.template_id)
    if tpl is None:
        raise HTTPException(404, "not found")
    from .meetings import download_name, export_data
    work = storage.workdir()
    try:
        out = os.path.join(work, "minutes.docx")
        drafter.render(storage.store().local_copy(tpl.storage_key, work), export_data(mt), out)
        accessibility.set_properties(out, ("%s minutes: %s %s" % (org.name, mt.title, mt.meeting_date)).strip()[:250], "en-US")
        with open(out, "rb") as fh:
            data = fh.read()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return Response(data, media_type=DOCX, headers={"Content-Disposition": 'attachment; filename="%s"' % download_name(mt, "docx"),
                                                    "Cache-Control": "no-store"})
