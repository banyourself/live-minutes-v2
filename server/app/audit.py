from . import models


def log(db, action, user=None, org_id=None, ip="", **detail):
    db.add(models.AuditEvent(action=action, user_id=user.id if user else None, org_id=org_id,
                             ip=ip, detail=detail))
