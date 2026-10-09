import calendar
import time

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select

from minutes_app import llm

from . import free_ai, models, personal, prompts
from .db import SessionLocal
from .security import decrypt, public_address
from .settings import settings

FREE = "builtin"
FREE_TIMEOUT = 3 * 3600


def month_start(ts=None):
    t = time.gmtime(ts or time.time())
    return float(calendar.timegm((t.tm_year, t.tm_mon, 1, 0, 0, 0)))


def policy_allows(db, org, key, default=True):
    district = db.get(models.District, org.district_id)
    school = db.get(models.School, org.school_id) if org.school_id else None
    for holder in (district, school):
        if holder is not None and (holder.settings or {}).get(key) is False:
            return False
    return default


def free_enabled():
    return bool(settings.free_ai_url and settings.free_ai_models)


def is_free(conn):
    return conn is not None and conn.provider == FREE


def free_label(model, first):
    return "Free AI: " + free_ai.name_for(model) + (" (recommended)" if first else "")


def free_conns(db):
    if not free_enabled():
        return []
    rows = {r.model: r for r in db.scalars(select(models.AIConnection).where(models.AIConnection.owner_scope == "platform",
                                                                            models.AIConnection.provider == FREE))}
    return [rows[m] for m in settings.free_ai_models if m in rows]


def free_conn(db):
    rows = free_conns(db)
    return rows[0] if rows else None


def free_ids(db):
    return [r.id for r in free_conns(db)]


def free_conn_id(db):
    row = free_conn(db)
    return row.id if row is not None else None


def ensure_free_conn():
    if not free_enabled():
        return None
    with SessionLocal() as s:
        rows = {r.model: r for r in s.scalars(select(models.AIConnection).where(models.AIConnection.owner_scope == "platform",
                                                                               models.AIConnection.provider == FREE))}
        for i, model in enumerate(settings.free_ai_models):
            row = rows.get(model)
            if row is None:
                s.add(models.AIConnection(owner_scope="platform", owner_id="", label=free_label(model, i == 0), provider=FREE,
                                          model=model, base_url="", api_key_enc="", created_by=""))
            else:
                row.label = free_label(model, i == 0)
        s.commit()
    with SessionLocal() as s:
        return free_conn_id(s)


def available(db, user, org):
    user_id = user.id if user is not None else ""
    own = [and_(models.AIConnection.owner_scope == "org", models.AIConnection.owner_id == org.id)]
    if user is not None and policy_allows(db, org, "allow_personal_ai"):
        own.append(and_(models.AIConnection.owner_scope == "user", models.AIConnection.owner_id == user.id))
    rows = {c.id: c for c in db.scalars(select(models.AIConnection).where(or_(*own)))}
    shared = []
    if org.school_id:
        shared.append(and_(models.AIConnection.owner_scope == "school", models.AIConnection.owner_id == org.school_id,
                           or_(and_(models.AIShare.target_scope == "org", models.AIShare.target_id == org.id),
                               models.AIShare.target_scope == "school_all",
                               and_(models.AIShare.target_scope == "user", models.AIShare.target_id == user_id))))
    shared.append(and_(models.AIConnection.owner_scope == "district", models.AIConnection.owner_id == org.district_id,
                       or_(and_(models.AIShare.target_scope == "school", models.AIShare.target_id == (org.school_id or "-")),
                           models.AIShare.target_scope == "district_all")))
    for c in db.scalars(select(models.AIConnection).join(models.AIShare, models.AIShare.connection_id == models.AIConnection.id)
                        .where(or_(*shared))):
        rows[c.id] = c
    for free in free_conns(db):
        rows[free.id] = free
    return list(rows.values())


def usable_for_org(db, conn, org, user=None):
    if conn is None:
        return False
    if is_free(conn):
        return free_enabled() and conn.model in settings.free_ai_models
    if conn.owner_scope == "user":
        owner = db.get(models.User, conn.owner_id)
        member = db.scalar(select(models.Membership).where(models.Membership.user_id == conn.owner_id,
                                                           models.Membership.org_id == org.id))
        return owner is not None and member is not None and policy_allows(db, org, "allow_personal_ai")
    return any(c.id == conn.id for c in available(db, user, org))


def chain(org, user=None):
    out = [("user", user.id)] if user is not None else []
    out.append(("org", org.id))
    if org.school_id:
        out.append(("school", org.school_id))
    out += [("district", org.district_id), ("platform", "")]
    return out


def setting(db, scope_name, scope_id, task):
    return db.scalar(select(models.AITaskSetting).where(models.AITaskSetting.scope == scope_name,
                                                        models.AITaskSetting.scope_id == scope_id,
                                                        models.AITaskSetting.task == task))


def resolve_connection(db, user, org, task):
    avail = {c.id: c for c in available(db, user, org)}
    for scope_name, scope_id in chain(org, user):
        row = setting(db, scope_name, scope_id, task)
        if row is not None and row.connection_id in avail:
            return avail[row.connection_id], scope_name
    org_owned = [c for c in avail.values() if c.owner_scope == "org"]
    if org_owned:
        return sorted(org_owned, key=lambda c: c.created_at)[0], "org"
    rest = [c for c in avail.values() if c.owner_scope != "user" and not is_free(c)]
    if rest:
        return sorted(rest, key=lambda c: c.created_at)[0], rest[0].owner_scope
    free = free_conn(db)
    if free is not None and free.id in avail:
        return free, "platform"
    return None, ""


def personal_org(db, org):
    return org is not None and personal.is_personal_district(db.get(models.District, org.district_id))


def resolve_prompt(db, org, task):
    for scope_name, scope_id in chain(org):
        row = setting(db, scope_name, scope_id, task)
        if row is not None and row.prompt:
            return row.prompt, scope_name
    return prompts.default_prompt(task, personal_org(db, org)), "default"


def context_for(db, org):
    return prompts.context_for(personal_org(db, org))


def platform_prompt(db, task):
    row = setting(db, "platform", "", task)
    return (row.prompt, "platform") if row is not None and row.prompt else (prompts.TASKS[task]["prompt"], "default")


def org_usage(db, org_id, since):
    tokens, cents = db.execute(select(func.coalesce(func.sum(models.AIUsage.input_tokens + models.AIUsage.output_tokens), 0),
                                      func.coalesce(func.sum(models.AIUsage.cost_cents), 0.0))
                               .where(models.AIUsage.org_id == org_id, models.AIUsage.created_at >= since)).one()
    return int(tokens or 0), float(cents or 0.0)


def over_limit(db, org):
    cfg = org.settings or {}
    tokens_cap, cents_cap = cfg.get("ai_limit_tokens"), cfg.get("ai_limit_cents")
    if not tokens_cap and not cents_cap:
        return ""
    tokens, cents = org_usage(db, org.id, month_start())
    if tokens_cap and tokens >= tokens_cap:
        return "%s reached its monthly AI limit of %s tokens; ask your college IT to raise it" % (org.name, f"{tokens_cap:,}")
    if cents_cap and cents >= cents_cap:
        return "%s reached its monthly AI limit of $%.2f; ask your college IT to raise it" % (org.name, cents_cap / 100)
    return ""


def price_for(db, provider, model):
    rows = db.scalars(select(models.AIPrice).where(models.AIPrice.provider == provider)).all()
    exact = next((r for r in rows if r.model == model), None)
    return exact or next((r for r in rows if r.model == "*"), None)


def recorder(org_id, user_id, conn, task):
    def record(usage):
        with SessionLocal() as s:
            price = price_for(s, conn.provider, conn.model)
            cost = 0.0
            if price is not None:
                cost = (usage["input_tokens"] * price.input_per_mtok_cents + usage["output_tokens"] * price.output_per_mtok_cents) / 1_000_000
            s.add(models.AIUsage(org_id=org_id, user_id=user_id, connection_id=conn.id, owner_scope=conn.owner_scope,
                                 task=task, provider=conn.provider, model=conn.model,
                                 input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"],
                                 cost_cents=cost, priced=price is not None))
            s.commit()
    return record


def gate(org_id):
    def check():
        with SessionLocal() as s:
            org = s.get(models.Organization, org_id)
            reason = over_limit(s, org) if org is not None else ""
        if reason:
            raise llm.LLMError(reason)
    return check


def creds_for(conn, org_id, user_id, task):
    if is_free(conn):
        return {"base_url": settings.free_ai_url, "guard": None, "timeout": FREE_TIMEOUT, "context": settings.free_ai_context,
                "meter": recorder(org_id, user_id, conn, task), "before": gate(org_id)}
    return {"api_key": decrypt(conn.api_key_enc), "base_url": conn.base_url, "guard": public_address,
            "meter": recorder(org_id, user_id, conn, task), "before": gate(org_id)}


def ask(db, user, org, task, material, extra="", max_tokens=2000, context=None):
    conn, _ = resolve_connection(db, user, org, task)
    if conn is None:
        raise HTTPException(400, "no AI is set up for %s in %s; add or choose one under Settings, AI" % (
            prompts.TASKS[task]["label"].lower(), org.name))
    reason = over_limit(db, org)
    if reason:
        raise HTTPException(429, reason)
    task_prompt, _ = resolve_prompt(db, org, task)
    system = prompts.system_prompt(task_prompt, extra, context or context_for(db, org))
    if is_free(conn):
        return free_ai.ask(db, user, org, task, conn, system, material, max_tokens), conn
    try:
        return llm.complete(conn.provider, conn.model, system, material,
                            max_tokens=max_tokens, creds=creds_for(conn, org.id, user.id if user else None, task)), conn
    except llm.LLMError as exc:
        raise HTTPException(502, "the AI could not finish: %s" % str(exc)[:300])
