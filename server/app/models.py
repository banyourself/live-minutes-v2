import time
import uuid

from sqlalchemy import JSON, BigInteger, Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

ROLES = ("owner", "secretary", "member", "viewer")
ACCOUNT_TYPES = ("student", "faculty", "staff", "it", "personal")
STAFF_TYPES = ("faculty", "staff", "it")
IT_TYPES = ("staff", "it")
ROLE_RANK = {"viewer": 0, "member": 1, "secretary": 2, "owner": 3}


def new_id():
    return uuid.uuid4().hex


def now():
    return time.time()


class District(Base):
    __tablename__ = "districts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    allowed_domains: Mapped[list] = mapped_column(JSON, default=list)
    staff_domains: Mapped[list] = mapped_column(JSON, default=list)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    district_id: Mapped[str] = mapped_column(ForeignKey("districts.id", ondelete="CASCADE"), index=True)
    school_id: Mapped[str | None] = mapped_column(ForeignKey("schools.id", ondelete="SET NULL"), nullable=True,
                                                  index=True)
    school: Mapped[str] = mapped_column(String(200), default="")
    name: Mapped[str] = mapped_column(String(200))
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class School(Base):
    __tablename__ = "schools"
    __table_args__ = (UniqueConstraint("district_id", "slug"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    district_id: Mapped[str] = mapped_column(ForeignKey("districts.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(120))
    email_domains: Mapped[list] = mapped_column(JSON, default=list)
    staff_domains: Mapped[list] = mapped_column(JSON, default=list)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class SchoolEmail(Base):
    __tablename__ = "school_emails"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    verified_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    code_hash: Mapped[str] = mapped_column(String(64), default="")
    code_expires_at: Mapped[float] = mapped_column(Float, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class JoinRequest(Base):
    __tablename__ = "join_requests"
    __table_args__ = (UniqueConstraint("org_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    school_email: Mapped[str] = mapped_column(String(320))
    message: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[float] = mapped_column(Float, default=now)
    decided_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decided_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class SchoolRequest(Base):
    __tablename__ = "school_requests"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(20), default="school")
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    school_id: Mapped[str | None] = mapped_column(ForeignKey("schools.id", ondelete="SET NULL"), nullable=True)
    district_id: Mapped[str | None] = mapped_column(ForeignKey("districts.id", ondelete="SET NULL"), nullable=True)
    district_name: Mapped[str] = mapped_column(String(200), default="")
    school_name: Mapped[str] = mapped_column(String(200))
    org_name: Mapped[str] = mapped_column(String(200))
    school_email: Mapped[str] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    note: Mapped[str] = mapped_column(String(500), default="")
    org_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    decided_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decided_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    last_login_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    email_verified_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    verified_via: Mapped[str] = mapped_column(String(20), default="")
    password_changed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    account_type: Mapped[str] = mapped_column(String(20), default="")
    terms_version: Mapped[str] = mapped_column(String(20), default="")
    terms_accepted_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    totp_secret_enc: Mapped[str] = mapped_column(Text, default="")
    totp_pending_enc: Mapped[str] = mapped_column(Text, default="")
    totp_enabled_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    totp_last_step: Mapped[int] = mapped_column(BigInteger, default=0)
    recovery_codes: Mapped[list] = mapped_column(JSON, default=list)


class Identity(Base):
    __tablename__ = "identities"
    __table_args__ = (UniqueConstraint("provider", "subject"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    subject: Mapped[str] = mapped_column(String(300))
    email: Mapped[str] = mapped_column(String(320), default="")
    created_at: Mapped[float] = mapped_column(Float, default=now)
    last_used_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class EmailToken(Base):
    __tablename__ = "email_tokens"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    expires_at: Mapped[float] = mapped_column(Float)
    used_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class OutboxEmail(Base):
    __tablename__ = "outbox"
    __table_args__ = (Index("ix_outbox_pending", "sent_at", "next_try_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    to_addr: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    next_try_at: Mapped[float] = mapped_column(Float, default=now)
    sent_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")


class RateEvent(Base):
    __tablename__ = "rate_events"
    __table_args__ = (Index("ix_rate_key_time", "key", "created_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(400))
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "org_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Invite(Base):
    __tablename__ = "invites"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(20), default="member")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[float] = mapped_column(Float, default=now)
    accepted_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    expires_at: Mapped[float] = mapped_column(Float)
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    last_seen_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    sudo_until: Mapped[float | None] = mapped_column(Float, nullable=True)


class PlatformSetting(Base):
    __tablename__ = "platform_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[float] = mapped_column(Float, default=now)
    updated_by: Mapped[str | None] = mapped_column(String(32), nullable=True)


class AIConnection(Base):
    __tablename__ = "ai_connections"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True,
                                               nullable=True)
    owner_scope: Mapped[str] = mapped_column(String(20), default="org")
    owner_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    label: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[str] = mapped_column(String(500), default="")
    api_key_enc: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[float] = mapped_column(Float, default=now)


class ZoomConnection(Base):
    __tablename__ = "zoom_connections"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), unique=True)
    host_email: Mapped[str] = mapped_column(String(320), default="")
    zoom_user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    zoom_account_id: Mapped[str] = mapped_column(String(64), default="")
    token_enc: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[float] = mapped_column(Float, default=now)


class ZoomPending(Base):
    __tablename__ = "zoom_pending"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    host_email: Mapped[str] = mapped_column(String(320), default="")
    zoom_user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    zoom_account_id: Mapped[str] = mapped_column(String(64), default="")
    token_enc: Mapped[str] = mapped_column(Text)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    expires_at: Mapped[float] = mapped_column(Float, default=0.0)


class ReferenceTranscript(Base):
    __tablename__ = "reference_transcripts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(60), default="")
    filename: Mapped[str] = mapped_column(String(200), default="")
    text: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Template(Base):
    __tablename__ = "templates"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(200))
    storage_key: Mapped[str] = mapped_column(String(300))
    mode: Mapped[str] = mapped_column(String(20))
    purpose: Mapped[str] = mapped_column(String(20), default="template")
    example_text: Mapped[str] = mapped_column(Text, default="")
    design: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (UniqueConstraint("series_id", "scheduled_at", name="uq_meetings_series_slot"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    meeting_date: Mapped[str] = mapped_column(String(80), default="")
    template_id: Mapped[str] = mapped_column(ForeignKey("templates.id"))
    ai_connection_id: Mapped[str | None] = mapped_column(ForeignKey("ai_connections.id", ondelete="SET NULL"),
                                                          nullable=True)
    run_mode: Mapped[str] = mapped_column(String(10), default="live")
    status: Mapped[str] = mapped_column(String(20), default="open")
    notes: Mapped[str] = mapped_column(Text, default="")
    draft: Mapped[dict] = mapped_column(JSON, default=dict)
    draft_rev: Mapped[int] = mapped_column(Integer, default=0)
    problems: Mapped[list] = mapped_column(JSON, default=list)
    drafted_upto: Mapped[int] = mapped_column(Integer, default=0)
    drafted_at: Mapped[float] = mapped_column(Float, default=0.0)
    draft_status: Mapped[str] = mapped_column(String(20), default="idle")
    draft_error: Mapped[str] = mapped_column(Text, default="")
    snapshot_tail: Mapped[list] = mapped_column(JSON, default=list)
    export_key: Mapped[str] = mapped_column(String(300), default="")
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[float] = mapped_column(Float, default=now)
    updated_at: Mapped[float] = mapped_column(Float, default=now)
    approved_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    approved_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_status: Mapped[str] = mapped_column(String(20), default="")
    review_note: Mapped[str] = mapped_column(Text, default="")
    review_requested_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    scheduled_at: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    duration_min: Mapped[int] = mapped_column(Integer, default=60)
    timezone: Mapped[str] = mapped_column(String(64), default="")
    zoom_url: Mapped[str] = mapped_column(String(500), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    series_id: Mapped[str | None] = mapped_column(ForeignKey("meeting_series.id", ondelete="SET NULL",
                                                             name="fk_meetings_series_id"), nullable=True, index=True)
    plain_summary: Mapped[str] = mapped_column(Text, default="")
    plain_summary_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    plain_summary_rev: Mapped[int] = mapped_column(Integer, default=0)
    reminded_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    visibility: Mapped[str] = mapped_column(String(10), default="private")
    recording_key: Mapped[str] = mapped_column(String(300), default="")
    recording_type: Mapped[str] = mapped_column(String(60), default="")
    recording_name: Mapped[str] = mapped_column(String(200), default="")
    recording_size: Mapped[int] = mapped_column(BigInteger, default=0)
    recording_link: Mapped[str] = mapped_column(String(500), default="")
    zoom_recording_uuid: Mapped[str] = mapped_column(String(200), default="", index=True)
    zoom_text_source: Mapped[str] = mapped_column(String(20), default="")
    sample: Mapped[bool] = mapped_column(Boolean, default=False)


class TranscriptLine(Base):
    __tablename__ = "transcript_lines"
    __table_args__ = (Index("ix_lines_meeting_seq", "meeting_id", "seq"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    t: Mapped[float | None] = mapped_column(Float, nullable=True)
    speaker: Mapped[str] = mapped_column(String(200), default="")
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20))
    updated_at: Mapped[float] = mapped_column(Float, default=now)


class CaptureToken(Base):
    __tablename__ = "capture_tokens"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[float] = mapped_column(Float, default=now)
    last_used_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_created", "status", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="update")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    run_after: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class FreeAIRun(Base):
    __tablename__ = "free_ai_runs"
    __table_args__ = (Index("ix_free_ai_runs_status_created", "status", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    task: Mapped[str] = mapped_column(String(20))
    ref: Mapped[str] = mapped_column(String(32), default="", index=True)
    connection_id: Mapped[str] = mapped_column(String(32), default="")
    model: Mapped[str] = mapped_column(String(200), default="")
    system: Mapped[str] = mapped_column(Text, default="")
    material: Mapped[str] = mapped_column(Text, default="")
    max_tokens: Mapped[int] = mapped_column(Integer, default=1000)
    prompt_chars: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    phase: Mapped[str] = mapped_column(String(20), default="waiting")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[float] = mapped_column(Float, default=now)
    started_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_token_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[float] = mapped_column(Float, default=now)


ADMIN_SCOPES = ("district", "school")


class AdminRole(Base):
    __tablename__ = "admin_roles"
    __table_args__ = (UniqueConstraint("user_id", "scope", "target_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scope: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[str] = mapped_column(String(32), index=True)
    staff_email: Mapped[str] = mapped_column(String(320), default="")
    granted_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500), default="")
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    interval: Mapped[str] = mapped_column(String(10), default="month")
    seat_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"), index=True)
    scope: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    seats: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    interval: Mapped[str] = mapped_column(String(10), default="month")
    started_at: Mapped[float] = mapped_column(Float, default=now)
    renews_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    canceled_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(String(500), default="")
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[float] = mapped_column(Float, default=now)
    updated_at: Mapped[float] = mapped_column(Float, default=now)


AI_TASKS = ("minutes", "questions", "translate", "summary")
AI_SCOPES = ("platform", "district", "school", "org", "user")


class AIShare(Base):
    __tablename__ = "ai_shares"
    __table_args__ = (UniqueConstraint("connection_id", "target_scope", "target_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    connection_id: Mapped[str] = mapped_column(ForeignKey("ai_connections.id", ondelete="CASCADE"), index=True)
    target_scope: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[str] = mapped_column(String(32), default="")
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[float] = mapped_column(Float, default=now)


class AITaskSetting(Base):
    __tablename__ = "ai_task_settings"
    __table_args__ = (UniqueConstraint("scope", "scope_id", "task"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(20))
    scope_id: Mapped[str] = mapped_column(String(32), default="")
    task: Mapped[str] = mapped_column(String(20))
    connection_id: Mapped[str | None] = mapped_column(ForeignKey("ai_connections.id", ondelete="SET NULL"),
                                                      nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[float] = mapped_column(Float, default=now)


class AIUsage(Base):
    __tablename__ = "ai_usage"
    __table_args__ = (Index("ix_ai_usage_org_time", "org_id", "created_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    connection_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    owner_scope: Mapped[str] = mapped_column(String(20), default="")
    task: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(200))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_cents: Mapped[float] = mapped_column(Float, default=0.0)
    priced: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[float] = mapped_column(Float, default=now, index=True)


class AIPrice(Base):
    __tablename__ = "ai_prices"
    __table_args__ = (UniqueConstraint("provider", "model"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(200))
    input_per_mtok_cents: Mapped[float] = mapped_column(Float, default=0.0)
    output_per_mtok_cents: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[float] = mapped_column(Float, default=now)


POSITION_PERMISSIONS = ("assign_officers", "remove_officers", "edit_permissions", "review_minutes", "manage_funding",
                        "delete_organization")


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("org_id", "name"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    rank: Mapped[int] = mapped_column(Integer, default=50)
    access: Mapped[str] = mapped_column(String(20), default="member")
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    account_types: Mapped[list] = mapped_column(JSON, default=list)
    max_holders: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class PositionTerm(Base):
    __tablename__ = "position_terms"
    __table_args__ = (Index("ix_terms_org_user", "org_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    position_id: Mapped[str] = mapped_column(ForeignKey("positions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    starts_at: Mapped[float] = mapped_column(Float, default=now)
    ends_at: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    remove_at_end: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[float] = mapped_column(Float, default=now)
    ended_at: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    ended_by: Mapped[str] = mapped_column(String(32), default="")
    end_reason: Mapped[str] = mapped_column(String(40), default="")


class MeetingSeries(Base):
    __tablename__ = "meeting_series"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    template_id: Mapped[str | None] = mapped_column(ForeignKey("templates.id", ondelete="SET NULL"), nullable=True)
    ai_connection_id: Mapped[str | None] = mapped_column(ForeignKey("ai_connections.id", ondelete="SET NULL"),
                                                          nullable=True)
    run_mode: Mapped[str] = mapped_column(String(10), default="live")
    notes: Mapped[str] = mapped_column(Text, default="")
    frequency: Mapped[str] = mapped_column(String(20), default="weekly")
    interval: Mapped[int] = mapped_column(Integer, default=1)
    weekdays: Mapped[list] = mapped_column(JSON, default=list)
    month_week: Mapped[int] = mapped_column(Integer, default=1)
    month_weekday: Mapped[int] = mapped_column(Integer, default=0)
    start_date: Mapped[str] = mapped_column(String(10))
    until_date: Mapped[str] = mapped_column(String(10), default="")
    start_time: Mapped[str] = mapped_column(String(5))
    timezone: Mapped[str] = mapped_column(String(64))
    duration_min: Mapped[int] = mapped_column(Integer, default=60)
    zoom_url: Mapped[str] = mapped_column(String(500), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    skip_dates: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[float] = mapped_column(Float, default=now)


class CalendarFeed(Base):
    __tablename__ = "calendar_feeds"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    last_used_at: Mapped[float | None] = mapped_column(Float, nullable=True)


MOTION_RESULTS = ("", "passed", "failed", "tabled", "withdrawn")
MOTION_METHODS = ("voice", "roll_call", "consent", "unanimous", "hands")
VOTE_VALUES = ("yes", "no", "abstain", "absent", "present")
FUNDING_STATES = ("submitted", "in_review", "approved", "denied", "paid", "withdrawn")


class MotionRecord(Base):
    __tablename__ = "motion_records"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    t: Mapped[float | None] = mapped_column(Float, nullable=True)
    under: Mapped[str] = mapped_column(String(300), default="")
    text: Mapped[str] = mapped_column(Text)
    mover: Mapped[str] = mapped_column(String(200), default="")
    seconder: Mapped[str] = mapped_column(String(200), default="")
    method: Mapped[str] = mapped_column(String(20), default="voice")
    result: Mapped[str] = mapped_column(String(20), default="")
    votes: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_by: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[float] = mapped_column(Float, default=now)


class FundingRequest(Base):
    __tablename__ = "funding_requests"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    requester: Mapped[str] = mapped_column(String(200), default="")
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    approved_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    purpose: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="submitted")
    motion_id: Mapped[str | None] = mapped_column(ForeignKey("motion_records.id", ondelete="SET NULL",
                                                             name="fk_funding_motion"), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[float] = mapped_column(Float, default=now)
    updated_at: Mapped[float] = mapped_column(Float, default=now)
    decided_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class MeetingTranslation(Base):
    __tablename__ = "meeting_translations"
    __table_args__ = (UniqueConstraint("meeting_id", "language"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[str] = mapped_column(String(32), index=True)
    language: Mapped[str] = mapped_column(String(20))
    draft: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str] = mapped_column(Text, default="")
    source_rev: Mapped[int] = mapped_column(Integer, default=0)
    ai_label: Mapped[str] = mapped_column(String(200), default="")
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[float] = mapped_column(Float, default=now)


NOTIFY_KINDS = ("draft_ready", "review_needed", "review_done", "reminder", "digest", "officer")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_time", "user_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    org_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[float] = mapped_column(Float, default=now)
    read_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class NotificationPref(Base):
    __tablename__ = "notification_prefs"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    email: Mapped[dict] = mapped_column(JSON, default=dict)
    digest_weekday: Mapped[int] = mapped_column(Integer, default=0)
    last_digest_at: Mapped[float] = mapped_column(Float, default=0.0)


class LibraryTemplate(Base):
    __tablename__ = "library_templates"
    __table_args__ = (Index("ix_library_owner", "owner_scope", "owner_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_scope: Mapped[str] = mapped_column(String(20))
    owner_id: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    filename: Mapped[str] = mapped_column(String(200))
    storage_key: Mapped[str] = mapped_column(String(300))
    mode: Mapped[str] = mapped_column(String(20))
    uses: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[float] = mapped_column(Float, default=now)


HOLD_SCOPES = ("district", "school", "org")


class LegalHold(Base):
    __tablename__ = "legal_holds"
    __table_args__ = (Index("ix_holds_target", "scope", "target_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    district_id: Mapped[str] = mapped_column(String(32), index=True)
    scope: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[float] = mapped_column(Float, default=now)
    released_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    released_by: Mapped[str] = mapped_column(String(32), default="")


class ExportJob(Base):
    __tablename__ = "export_jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[str] = mapped_column(String(32), index=True)
    requested_by: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    storage_key: Mapped[str] = mapped_column(String(300), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[float] = mapped_column(Float, default=now)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)


BACKUP_KINDS = ("s3", "azure")
BACKUP_SCHEDULES = ("daily", "weekly", "manual")


class BackupTarget(Base):
    __tablename__ = "backup_targets"
    __table_args__ = (Index("ix_backup_scope", "scope", "target_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    secret: Mapped[str] = mapped_column(Text, default="")
    data_kinds: Mapped[list] = mapped_column(JSON, default=list)
    schedule: Mapped[str] = mapped_column(String(20), default="weekly")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[float] = mapped_column(Float, default=now)
    last_run_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class BackupRun(Base):
    __tablename__ = "backup_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    backup_id: Mapped[str] = mapped_column(ForeignKey("backup_targets.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    trigger: Mapped[str] = mapped_column(String(20), default="schedule")
    object_key: Mapped[str] = mapped_column(String(500), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[float] = mapped_column(Float, default=now)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class PersonalToken(Base):
    __tablename__ = "personal_tokens"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    can_write: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    expires_at: Mapped[float] = mapped_column(Float)
    last_used_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    client_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    refresh_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    refresh_prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    refresh_expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class AssistantAction(Base):
    __tablename__ = "assistant_actions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    title: Mapped[str] = mapped_column(String(300))
    lines: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    result: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[float] = mapped_column(Float, default=now)
    decided_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class DraftRevision(Base):
    __tablename__ = "draft_revisions"
    __table_args__ = (Index("ix_draft_revisions_meeting_time", "meeting_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    rev: Mapped[int] = mapped_column(Integer, default=0)
    draft: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    label: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[float] = mapped_column(Float, default=now)


class OAuthClient(Base):
    __tablename__ = "oauth_clients"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    redirect_uris: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    last_used_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class OAuthCode(Base):
    __tablename__ = "oauth_codes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    client_id: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    redirect_uri: Mapped[str] = mapped_column(String(500))
    challenge: Mapped[str] = mapped_column(String(128))
    can_write: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[float] = mapped_column(Float)
    used_at: Mapped[float | None] = mapped_column(Float, nullable=True)

