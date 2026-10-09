import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from minutes_app import llm

from .. import ai_runtime, audit, free_ai, models, personal, prompts, ratelimit, scope
from ..db import get_db
from ..deps import client_ip, current_user, platform_admin, require_role
from ..security import check_outbound_url, encrypt, mask, decrypt

router = APIRouter(tags=["ai"])
OWNER_SCOPES = ("district", "school", "org", "user")
SHARE_TARGETS = {"district": ("school", "district_all"), "school": ("org", "user", "school_all")}


class ConnIn(BaseModel):
    label: str = ""
    provider: str
    model: str
    base_url: str = ""
    api_key: str = ""
    scope: str = "org"
    scope_id: str = ""


class ConnPatch(BaseModel):
    label: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None


class ShareIn(BaseModel):
    target_scope: str
    target_id: str = ""


class TaskIn(BaseModel):
    scope: str
    scope_id: str = ""
    task: str
    connection_id: str | None = None
    prompt: str | None = None
    clear_connection: bool = False
    clear_prompt: bool = False


class LimitIn(BaseModel):
    tokens: int | None = None
    cents: int | None = None


class PolicyIn(BaseModel):
    scope: str
    scope_id: str
    allow_personal_ai: bool


class PriceIn(BaseModel):
    provider: str
    model: str
    input_per_mtok_cents: float
    output_per_mtok_cents: float


def catalog():
    rows = []
    for pid, (label, base, _key, needs_key) in llm.OPENAI_COMPATIBLE.items():
        rows.append({"id": pid, "label": label, "default_base_url": base, "needs_key": needs_key,
                     "needs_base_url": pid == "custom", "local": pid in ("lmstudio", "ollama")})
    label, base, _key, _ = llm.ANTHROPIC
    rows.insert(0, {"id": "anthropic", "label": label, "default_base_url": base, "needs_key": True,
                    "needs_base_url": False, "local": False})
    return rows


def owner_name(db, c):
    holder = {"district": models.District, "school": models.School, "org": models.Organization,
              "user": models.User}.get(c.owner_scope)
    if c.owner_scope == "platform":
        return "Live Minutes"
    row = db.get(holder, c.owner_id) if holder else None
    if row is None:
        return ""
    return getattr(row, "name", "") or getattr(row, "email", "")


def conn_payload(db, c, manage=False):
    key = decrypt(c.api_key_enc) if c.api_key_enc else ""
    out = {"id": c.id, "label": c.label, "provider": c.provider, "model": c.model, "base_url": c.base_url,
           "api_key": mask(key), "has_key": bool(key), "owner_scope": c.owner_scope, "owner_id": c.owner_id,
           "owner": owner_name(db, c), "can_manage": manage and not ai_runtime.is_free(c), "free": ai_runtime.is_free(c)}
    if manage and c.owner_scope in SHARE_TARGETS:
        out["shares"] = [share_payload(db, s) for s in db.scalars(select(models.AIShare).where(models.AIShare.connection_id == c.id))]
    return out


def share_payload(db, s):
    name = {"school_all": "Everyone at the college", "district_all": "Every college in the district"}.get(s.target_scope, "")
    if not name:
        holder = {"school": models.School, "org": models.Organization, "user": models.User}[s.target_scope]
        row = db.get(holder, s.target_id)
        name = (getattr(row, "name", "") or getattr(row, "email", "")) if row else "(removed)"
    return {"id": s.id, "target_scope": s.target_scope, "target_id": s.target_id, "target": name}


def resolve_base(provider, base_url):
    if provider == "anthropic":
        return ""
    if provider not in llm.OPENAI_COMPATIBLE:
        raise HTTPException(400, "unknown provider")
    default = llm.OPENAI_COMPATIBLE[provider][1]
    url = (base_url or default).strip()
    if not url:
        raise HTTPException(400, "enter the server URL for this provider")
    if url == default and provider not in ("lmstudio", "ollama"):
        return ""
    try:
        check_outbound_url(url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return "" if url == default else url


def can_manage(db, user, scope_name, scope_id):
    if scope_name == "platform":
        return user.is_platform_admin
    if scope_name == "district":
        return user.is_platform_admin or scope_id in scope.district_ids(db, user)
    if scope_name == "school":
        return user.is_platform_admin or scope_id in scope.school_ids(db, user)
    if scope_name == "org":
        try:
            require_role(db, user, scope_id, "secretary")
            return True
        except HTTPException:
            return False
    if scope_name == "user":
        return scope_id == user.id
    return False


def need_manage(db, user, scope_name, scope_id):
    if scope_name not in models.AI_SCOPES or not can_manage(db, user, scope_name, scope_id):
        raise HTTPException(404, "not found")


def owned_conn(db, user, conn_id):
    c = db.get(models.AIConnection, conn_id)
    if c is None or not can_manage(db, user, c.owner_scope, c.owner_id):
        raise HTTPException(404, "connection not found")
    if ai_runtime.is_free(c):
        raise HTTPException(400, "the free AI is part of Live Minutes; the server settings choose its model")
    return c


def audit_org(c):
    return c.owner_id if c.owner_scope == "org" else None


def create_conn(db, request, user, body, scope_name, scope_id):
    if scope_name not in OWNER_SCOPES:
        raise HTTPException(400, "choose who owns this AI")
    need_manage(db, user, scope_name, scope_id)
    base = resolve_base(body.provider, body.base_url)
    if not body.model.strip():
        raise HTTPException(400, "enter a model name")
    meta = next(p for p in catalog() if p["id"] == body.provider)
    if meta["needs_key"] and not body.api_key.strip():
        raise HTTPException(400, "this provider needs an API key")
    c = models.AIConnection(org_id=scope_id if scope_name == "org" else None, owner_scope=scope_name, owner_id=scope_id,
                            label=(body.label or meta["label"]).strip()[:120], provider=body.provider,
                            model=body.model.strip()[:200], base_url=base, api_key_enc=encrypt(body.api_key.strip()),
                            created_by=user.id)
    db.add(c)
    audit.log(db, "ai.added", user, audit_org(c), client_ip(request), owner=scope_name, owner_id=scope_id,
              provider=body.provider, model=c.model)
    db.commit()
    return conn_payload(db, c, True)


@router.get("/api/providers")
def providers():
    return {"providers": catalog()}


@router.get("/api/ai/available")
def available_here(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    org, _ = require_role(db, user, org_id, "member")
    rows = ai_runtime.available(db, user, org)
    return {"connections": [conn_payload(db, c, can_manage(db, user, c.owner_scope, c.owner_id)) for c in rows],
            "personal_allowed": ai_runtime.policy_allows(db, org, "allow_personal_ai")}


@router.get("/api/ai/owned")
def owned(scope: str, scope_id: str = "", user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    need_manage(db, user, scope, scope_id)
    rows = db.scalars(select(models.AIConnection).where(models.AIConnection.owner_scope == scope,
                                                        models.AIConnection.owner_id == scope_id)
                      .order_by(models.AIConnection.created_at)).all()
    return {"connections": [conn_payload(db, c, True) for c in rows]}


@router.post("/api/ai/connections")
def add_connection(body: ConnIn, request: Request, user: models.User = Depends(current_user),
                   db: Session = Depends(get_db)):
    return create_conn(db, request, user, body, body.scope, body.scope_id if body.scope != "user" else user.id)


@router.patch("/api/ai/connections/{conn_id}")
def edit_connection(conn_id: str, body: ConnPatch, request: Request, user: models.User = Depends(current_user),
                    db: Session = Depends(get_db)):
    c = owned_conn(db, user, conn_id)
    if body.label is not None:
        c.label = body.label.strip()[:120] or c.label
    if body.model is not None and body.model.strip():
        c.model = body.model.strip()[:200]
    if body.base_url is not None:
        new_base = resolve_base(c.provider, body.base_url)
        if new_base != c.base_url and c.api_key_enc and not body.api_key:
            raise HTTPException(400, "enter the API key again when you change the server address")
        c.base_url = new_base
    if body.api_key:
        c.api_key_enc = encrypt(body.api_key.strip())
    audit.log(db, "ai.updated", user, audit_org(c), client_ip(request), connection=c.id)
    db.commit()
    return conn_payload(db, c, True)


@router.delete("/api/ai/connections/{conn_id}")
def remove_connection(conn_id: str, request: Request, user: models.User = Depends(current_user),
                      db: Session = Depends(get_db)):
    c = owned_conn(db, user, conn_id)
    audit.log(db, "ai.deleted", user, audit_org(c), client_ip(request), connection=c.id)
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.post("/api/ai/connections/{conn_id}/test")
def test_connection(conn_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    c = owned_conn(db, user, conn_id)
    ratelimit.hit("ai-test:" + c.owner_id, 20, 600)
    try:
        reply = llm.complete(c.provider, c.model, "Reply with the single word OK.", "Say OK.", max_tokens=16,
                             creds={"api_key": decrypt(c.api_key_enc), "base_url": c.base_url,
                                    "guard": ai_runtime.public_address})
    except llm.LLMError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "reply": reply.strip()[:80]}


def check_share_target(db, c, target_scope, target_id):
    if target_scope not in SHARE_TARGETS.get(c.owner_scope, ()):
        raise HTTPException(400, "this AI cannot be shared that way")
    if target_scope in ("school_all", "district_all"):
        return ""
    if c.owner_scope == "district" and target_scope == "school":
        school = db.get(models.School, target_id)
        if school is None or school.district_id != c.owner_id:
            raise HTTPException(400, "choose a college in this district")
    if c.owner_scope == "school" and target_scope == "org":
        org = db.get(models.Organization, target_id)
        if org is None or org.school_id != c.owner_id:
            raise HTTPException(400, "choose an organization at this college")
    if c.owner_scope == "school" and target_scope == "user":
        at_school = db.scalar(select(models.Membership).join(models.Organization, models.Organization.id == models.Membership.org_id)
                              .where(models.Membership.user_id == target_id, models.Organization.school_id == c.owner_id))
        if at_school is None:
            raise HTTPException(400, "choose a person in an organization at this college")
    return target_id


@router.post("/api/ai/connections/{conn_id}/shares")
def add_share(conn_id: str, body: ShareIn, request: Request, user: models.User = Depends(current_user),
              db: Session = Depends(get_db)):
    c = owned_conn(db, user, conn_id)
    target_id = check_share_target(db, c, body.target_scope, body.target_id)
    exists = db.scalar(select(models.AIShare).where(models.AIShare.connection_id == c.id,
                                                    models.AIShare.target_scope == body.target_scope,
                                                    models.AIShare.target_id == target_id))
    if exists is None:
        exists = models.AIShare(connection_id=c.id, target_scope=body.target_scope, target_id=target_id,
                                created_by=user.id)
        db.add(exists)
        audit.log(db, "ai.shared", user, ip=client_ip(request), connection=c.id, target=body.target_scope + ":" + target_id)
        db.commit()
    return share_payload(db, exists)


@router.delete("/api/ai/shares/{share_id}")
def remove_share(share_id: str, request: Request, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    s = db.get(models.AIShare, share_id)
    if s is None:
        raise HTTPException(404, "not found")
    owned_conn(db, user, s.connection_id)
    audit.log(db, "ai.unshared", user, ip=client_ip(request), connection=s.connection_id,
              target=s.target_scope + ":" + s.target_id)
    db.delete(s)
    db.commit()
    return {"ok": True}


def choices_for(db, user, scope_name, scope_id):
    if scope_name == "district":
        rows = db.scalars(select(models.AIConnection).where(models.AIConnection.owner_scope == "district",
                                                            models.AIConnection.owner_id == scope_id)).all()
    elif scope_name == "school":
        school = db.get(models.School, scope_id)
        own = db.scalars(select(models.AIConnection).where(models.AIConnection.owner_scope == "school",
                                                           models.AIConnection.owner_id == scope_id)).all()
        shared = db.scalars(select(models.AIConnection).join(models.AIShare, models.AIShare.connection_id == models.AIConnection.id)
                            .where(models.AIConnection.owner_scope == "district",
                                   models.AIConnection.owner_id == (school.district_id if school else ""),
                                   ((models.AIShare.target_scope == "school") & (models.AIShare.target_id == scope_id))
                                   | (models.AIShare.target_scope == "district_all"))).all()
        rows = list({c.id: c for c in own + shared}.values())
    elif scope_name == "org":
        org = db.get(models.Organization, scope_id)
        rows = [c for c in ai_runtime.available(db, None, org)] if org else []
    elif scope_name == "user":
        mine = db.scalars(select(models.AIConnection).where(models.AIConnection.owner_scope == "user",
                                                            models.AIConnection.owner_id == user.id)).all()
        orgs = db.scalars(select(models.Organization).join(models.Membership, models.Membership.org_id == models.Organization.id)
                          .where(models.Membership.user_id == user.id)).all()
        shared = [c for o in orgs for c in ai_runtime.available(db, user, o) if c.owner_scope != "user"]
        rows = list({c.id: c for c in list(mine) + shared}.values())
    else:
        rows = []
    return rows


def inherited(db, scope_name, scope_id, task):
    if scope_name == "org":
        org = db.get(models.Organization, scope_id)
        parents = ai_runtime.chain(org)[1:] if org else [("platform", "")]
    elif scope_name == "school":
        school = db.get(models.School, scope_id)
        parents = [("district", school.district_id), ("platform", "")] if school else [("platform", "")]
    elif scope_name == "district":
        parents = [("platform", "")]
    else:
        parents = []
    ai = None
    for p_scope, p_id in parents:
        row = ai_runtime.setting(db, p_scope, p_id, task)
        if row is not None and row.connection_id and ai is None:
            conn = db.get(models.AIConnection, row.connection_id)
            if conn is not None:
                ai = {"label": conn.label, "from": p_scope}
    for p_scope, p_id in parents:
        row = ai_runtime.setting(db, p_scope, p_id, task)
        if row is not None and row.prompt:
            return {"prompt": row.prompt, "from": p_scope, "ai": ai}
    return {"prompt": prompts.TASKS[task]["prompt"], "from": "default", "ai": ai}


@router.get("/api/ai/tasks")
def task_settings(scope: str, scope_id: str = "", user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    scope_id = user.id if scope == "user" else scope_id
    need_manage(db, user, scope, scope_id)
    choices = choices_for(db, user, scope, scope_id)
    solo = scope == "org" and personal.is_personal(db, scope_id)
    out = []
    for task, meta in prompts.TASKS.items():
        row = ai_runtime.setting(db, scope, scope_id, task)
        out.append({"task": task, "label": meta["label"], "connection_id": row.connection_id if row else None,
                    "prompt": row.prompt if row and row.prompt else "", "inherited": inherited(db, scope, scope_id, task),
                    "default_prompt": prompts.default_prompt(task, solo)})
    return {"tasks": out, "choices": [conn_payload(db, c) for c in choices if c.owner_scope != "user" or scope == "user"],
            "can_edit_prompts": scope != "user", "context": prompts.context_for(solo)}


@router.put("/api/ai/tasks")
def save_task(body: TaskIn, request: Request, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    scope_id = user.id if body.scope == "user" else body.scope_id
    need_manage(db, user, body.scope, scope_id)
    if body.task not in prompts.TASKS:
        raise HTTPException(400, "unknown task")
    if body.prompt is not None and body.scope == "user":
        raise HTTPException(400, "prompts are set by your organization, college, or district")
    row = ai_runtime.setting(db, body.scope, scope_id, body.task)
    if row is None:
        row = models.AITaskSetting(scope=body.scope, scope_id=scope_id, task=body.task)
        db.add(row)
    if body.clear_connection:
        row.connection_id = None
    elif body.connection_id is not None:
        allowed = {c.id for c in choices_for(db, user, body.scope, scope_id)
                   if c.owner_scope != "user" or body.scope == "user"}
        if body.connection_id not in allowed:
            raise HTTPException(400, "choose an AI that is available here")
        row.connection_id = body.connection_id
    if body.clear_prompt:
        row.prompt = None
    elif body.prompt is not None:
        text = body.prompt.strip()
        if len(text) > 6000:
            raise HTTPException(400, "keep the prompt under 6,000 characters")
        row.prompt = text or None
    row.updated_by, row.updated_at = user.id, time.time()
    audit.log(db, "ai.task_setting", user, body.scope_id if body.scope == "org" else None, client_ip(request),
              scope=body.scope, scope_id=scope_id, task=body.task, connection=row.connection_id,
              prompt_changed=body.prompt is not None or body.clear_prompt)
    db.commit()
    return {"ok": True}


def orgs_under(db, scope_name, scope_id):
    stmt = select(models.Organization)
    if scope_name == "org":
        stmt = stmt.where(models.Organization.id == scope_id)
    elif scope_name == "school":
        stmt = stmt.where(models.Organization.school_id == scope_id)
    elif scope_name == "district":
        stmt = stmt.where(models.Organization.district_id == scope_id)
    return db.scalars(stmt.order_by(models.Organization.name)).all()


@router.get("/api/ai/usage")
def usage(scope: str, scope_id: str = "", user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if scope not in ("org", "school", "district", "platform"):
        raise HTTPException(400, "choose an organization, college, district, or the platform")
    if scope == "org":
        org, _ = require_role(db, user, scope_id, "secretary")
    else:
        need_manage(db, user, scope, scope_id)
    orgs = orgs_under(db, scope, scope_id) if scope != "platform" else []
    since = ai_runtime.month_start()
    filters = [models.AIUsage.created_at >= since]
    if scope != "platform":
        filters.append(models.AIUsage.org_id.in_([o.id for o in orgs] or [""]))
    tokens = func.coalesce(func.sum(models.AIUsage.input_tokens + models.AIUsage.output_tokens), 0)
    cents = func.coalesce(func.sum(models.AIUsage.cost_cents), 0.0)
    unpriced = func.coalesce(func.sum(case((models.AIUsage.priced.is_(False), 1), else_=0)), 0)
    total = db.execute(select(tokens, cents, func.count(), unpriced).where(*filters)).one()
    by_task = db.execute(select(models.AIUsage.task, tokens, cents, func.count()).where(*filters)
                         .group_by(models.AIUsage.task)).all()
    by_model = db.execute(select(models.AIUsage.provider, models.AIUsage.model, tokens, cents, func.count()).where(*filters)
                          .group_by(models.AIUsage.provider, models.AIUsage.model)).all()
    can_limit = scope in ("school", "district", "platform") or (scope == "org" and scope_covers_from_above(db, user, org))
    rows = []
    for o in orgs:
        used_tokens, used_cents = ai_runtime.org_usage(db, o.id, since)
        cfg = o.settings or {}
        rows.append({"id": o.id, "name": o.name, "school": o.school, "tokens": used_tokens, "cents": used_cents,
                     "limit_tokens": cfg.get("ai_limit_tokens"), "limit_cents": cfg.get("ai_limit_cents")})
    return {"since": since, "tokens": int(total[0]), "cents": float(total[1]), "calls": int(total[2]),
            "unpriced_calls": int(total[3]),
            "by_task": [{"task": t, "tokens": int(k), "cents": float(c), "calls": int(n)} for t, k, c, n in by_task],
            "by_model": [{"provider": pr, "model": m, "tokens": int(k), "cents": float(c), "calls": int(n)}
                         for pr, m, k, c, n in by_model],
            "orgs": rows, "can_set_limits": can_limit}


def scope_covers_from_above(db, user, org):
    if user.is_platform_admin:
        return True
    return org.district_id in scope.district_ids(db, user) or (bool(org.school_id) and org.school_id in scope.school_ids(db, user))


@router.put("/api/ai/limits/{org_id}")
def set_limits(org_id: str, body: LimitIn, request: Request, user: models.User = Depends(current_user),
               db: Session = Depends(get_db)):
    org = db.get(models.Organization, org_id)
    if org is None or not scope_covers_from_above(db, user, org):
        raise HTTPException(404, "organization not found")
    for value in (body.tokens, body.cents):
        if value is not None and (value < 0 or value > 10_000_000_000):
            raise HTTPException(400, "enter a limit of zero or more")
    cfg = dict(org.settings or {})
    cfg["ai_limit_tokens"] = body.tokens or None
    cfg["ai_limit_cents"] = body.cents or None
    org.settings = cfg
    audit.log(db, "ai.limits", user, org.id, client_ip(request), tokens=body.tokens, cents=body.cents)
    db.commit()
    return {"ok": True}


@router.put("/api/ai/policy")
def set_policy(body: PolicyIn, request: Request, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if body.scope not in ("district", "school"):
        raise HTTPException(400, "policies are set for a district or college")
    need_manage(db, user, body.scope, body.scope_id)
    holder = db.get(models.District if body.scope == "district" else models.School, body.scope_id)
    cfg = dict(holder.settings or {})
    cfg["allow_personal_ai"] = body.allow_personal_ai
    holder.settings = cfg
    audit.log(db, "ai.policy", user, ip=client_ip(request), scope=body.scope, scope_id=body.scope_id,
              allow_personal_ai=body.allow_personal_ai)
    db.commit()
    return {"ok": True}


@router.get("/api/ai/policy")
def get_policy(scope: str, scope_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    need_manage(db, user, scope, scope_id)
    holder = db.get(models.District if scope == "district" else models.School, scope_id)
    return {"allow_personal_ai": (holder.settings or {}).get("allow_personal_ai", True) if holder else True}


@router.get("/api/admin/ai-prices")
def prices(user: models.User = Depends(platform_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(models.AIPrice).order_by(models.AIPrice.provider, models.AIPrice.model)).all()
    used = db.execute(select(models.AIUsage.provider, models.AIUsage.model).distinct()).all()
    return {"prices": [{"id": r.id, "provider": r.provider, "model": r.model, "input_per_mtok_cents": r.input_per_mtok_cents,
                        "output_per_mtok_cents": r.output_per_mtok_cents} for r in rows],
            "models_in_use": [{"provider": p, "model": m} for p, m in used]}


@router.put("/api/admin/ai-prices")
def set_price(body: PriceIn, request: Request, user: models.User = Depends(platform_admin), db: Session = Depends(get_db)):
    if body.input_per_mtok_cents < 0 or body.output_per_mtok_cents < 0:
        raise HTTPException(400, "prices cannot be negative")
    row = db.scalar(select(models.AIPrice).where(models.AIPrice.provider == body.provider, models.AIPrice.model == body.model))
    if row is None:
        row = models.AIPrice(provider=body.provider.strip()[:40], model=body.model.strip()[:200] or "*")
        db.add(row)
    row.input_per_mtok_cents, row.output_per_mtok_cents = body.input_per_mtok_cents, body.output_per_mtok_cents
    row.updated_at = time.time()
    audit.log(db, "ai.price", user, ip=client_ip(request), provider=row.provider, model=row.model)
    db.commit()
    return {"ok": True}


@router.get("/api/free-ai/runs/{run_id}")
def free_run(run_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    ratelimit.hit("free-run:" + user.id, 120, 600)
    run = db.get(models.FreeAIRun, run_id[:32])
    if run is None or run.user_id != user.id:
        raise HTTPException(404, "not found")
    return free_ai.payload(db, run)


@router.delete("/api/free-ai/runs/{run_id}")
def cancel_free_run(run_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    run = db.get(models.FreeAIRun, run_id[:32])
    if run is None or run.user_id != user.id:
        raise HTTPException(404, "not found")
    if run.status != "queued":
        raise HTTPException(400, "it has already started; it will finish on its own")
    db.delete(run)
    db.commit()
    return {"ok": True}


@router.get("/api/orgs/{org_id}/ai")
def list_conns(org_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return available_here(org_id, user, db)


@router.post("/api/orgs/{org_id}/ai")
def add_conn(org_id: str, body: ConnIn, request: Request, user: models.User = Depends(current_user),
             db: Session = Depends(get_db)):
    require_role(db, user, org_id, "secretary")
    return create_conn(db, request, user, body, "org", org_id)


@router.delete("/api/orgs/{org_id}/ai/{conn_id}")
def delete_conn(org_id: str, conn_id: str, request: Request, user: models.User = Depends(current_user),
                db: Session = Depends(get_db)):
    c = owned_conn(db, user, conn_id)
    if c.owner_scope != "org" or c.owner_id != org_id:
        raise HTTPException(404, "connection not found")
    return remove_connection(conn_id, request, user, db)


@router.post("/api/orgs/{org_id}/ai/{conn_id}/test")
def test_conn(org_id: str, conn_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return test_connection(conn_id, user, db)
