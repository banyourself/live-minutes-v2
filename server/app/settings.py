import os
import sys
import urllib.parse
from dataclasses import dataclass, field

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _bool(name, default=False):
    return os.environ.get(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


def _list(name):
    return [x.strip() for x in os.environ.get(name, "").split(",") if x.strip()]


DEV = os.environ.get("LIVE_MINUTES_DEV") == "1"


def _https():
    return os.environ.get("PUBLIC_URL", "").lower().startswith("https://")


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(REPO_ROOT, "server-data", "live-minutes.db")))
    secret_key: str = field(default_factory=lambda: os.environ.get("SECRET_KEY", ""))
    public_url: str = field(default_factory=lambda: os.environ.get("PUBLIC_URL", "http://localhost:8000").rstrip("/"))
    storage_dir: str = field(default_factory=lambda: os.environ.get(
        "STORAGE_DIR", os.path.join(REPO_ROOT, "server-data", "files")))
    s3_bucket: str = field(default_factory=lambda: os.environ.get("S3_BUCKET", ""))
    web_dist: str = field(default_factory=lambda: os.environ.get(
        "WEB_DIST", os.path.join(REPO_ROOT, "web", "dist")))
    secure_cookies: bool = field(default_factory=lambda: _bool("SECURE_COOKIES", _https()))
    allow_signup: bool = field(default_factory=lambda: _bool("ALLOW_SIGNUP", DEV))
    allow_district_creation: bool = field(default_factory=lambda: _bool("ALLOW_DISTRICT_CREATION", DEV))
    allow_private_llm_urls: bool = field(default_factory=lambda: _bool("ALLOW_PRIVATE_LLM_URLS", False))
    backup_s3_hosts: list = field(default_factory=lambda: [h.lower() for h in _list("BACKUP_S3_HOSTS")])
    offsite_endpoint: str = field(default_factory=lambda: os.environ.get("OFFSITE_S3_ENDPOINT", "").rstrip("/"))
    offsite_bucket: str = field(default_factory=lambda: os.environ.get("OFFSITE_S3_BUCKET", ""))
    offsite_key_id: str = field(default_factory=lambda: os.environ.get("OFFSITE_S3_ACCESS_KEY_ID", ""))
    offsite_secret: str = field(default_factory=lambda: os.environ.get("OFFSITE_S3_SECRET_ACCESS_KEY", ""))
    offsite_public_key: str = field(default_factory=lambda: os.environ.get("OFFSITE_BACKUP_PUBLIC_KEY", ""))
    offsite_keep_days: int = field(default_factory=lambda: int(os.environ.get("OFFSITE_KEEP_DAYS", "30") or 30))
    backups_dir: str = field(default_factory=lambda: os.environ.get("BACKUPS_MOUNT", "/backups"))
    free_ai_url: str = field(default_factory=lambda: os.environ.get("FREE_AI_URL", "").rstrip("/"))
    libretranslate_url: str = field(default_factory=lambda: os.environ.get("LIBRETRANSLATE_URL", "").rstrip("/"))
    free_ai_models: list = field(default_factory=lambda: _list("FREE_AI_MODELS") or _list("FREE_AI_MODEL"))
    free_ai_context: int = field(default_factory=lambda: int(os.environ.get("FREE_AI_CONTEXT", "32768") or 32768))
    inline_worker: bool = field(default_factory=lambda: _bool("INLINE_WORKER", True))
    enable_api_docs: bool = field(default_factory=lambda: _bool("ENABLE_API_DOCS", DEV))
    cors_origins: list = field(default_factory=lambda: _list("CORS_ORIGINS"))
    allowed_hosts: list = field(default_factory=lambda: [h.lower() for h in _list("ALLOWED_HOSTS")])
    trusted_proxy_hops: int = field(default_factory=lambda: int(os.environ.get("TRUSTED_PROXY_HOPS", "0")))
    platform_admins: list = field(default_factory=lambda: [e.lower() for e in _list("PLATFORM_ADMIN_EMAILS")])
    encryption_keys: list = field(default_factory=lambda: _list("ENCRYPTION_KEYS"))
    live_lines: int = field(default_factory=lambda: int(os.environ.get("LIVE_LINES", "25")))
    live_seconds: int = field(default_factory=lambda: int(os.environ.get("LIVE_SECONDS", "90")))
    session_days: int = field(default_factory=lambda: int(os.environ.get("SESSION_DAYS", "14")))
    session_idle_hours: float = field(default_factory=lambda: float(os.environ.get("SESSION_IDLE_HOURS", "12")))
    invite_days: int = field(default_factory=lambda: int(os.environ.get("INVITE_DAYS", "7")))
    capture_token_days: int = field(default_factory=lambda: int(os.environ.get("CAPTURE_TOKEN_DAYS", "180")))
    max_request_mb: int = field(default_factory=lambda: int(os.environ.get("MAX_REQUEST_MB", "16")))
    mail_backend: str = field(default_factory=lambda: os.environ.get("MAIL_BACKEND", "console" if DEV else "none"))
    mail_from: str = field(default_factory=lambda: os.environ.get("MAIL_FROM", ""))
    smtp_host: str = field(default_factory=lambda: os.environ.get("SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(os.environ.get("SMTP_PORT", "587")))
    smtp_username: str = field(default_factory=lambda: os.environ.get("SMTP_USERNAME", ""))
    smtp_password: str = field(default_factory=lambda: os.environ.get("SMTP_PASSWORD", ""))
    smtp_starttls: bool = field(default_factory=lambda: _bool("SMTP_STARTTLS", True))
    email_dns_check: bool = field(default_factory=lambda: _bool("EMAIL_DNS_CHECK", not DEV))
    password_breach_check: bool = field(default_factory=lambda: _bool("PASSWORD_BREACH_CHECK", not DEV))
    turnstile_site_key: str = field(default_factory=lambda: os.environ.get("TURNSTILE_SITE_KEY", ""))
    turnstile_secret: str = field(default_factory=lambda: os.environ.get("TURNSTILE_SECRET_KEY", ""))
    google_client_id: str = field(default_factory=lambda: os.environ.get("GOOGLE_CLIENT_ID", ""))
    google_client_secret: str = field(default_factory=lambda: os.environ.get("GOOGLE_CLIENT_SECRET", ""))
    microsoft_client_id: str = field(default_factory=lambda: os.environ.get("MICROSOFT_CLIENT_ID", ""))
    microsoft_client_secret: str = field(default_factory=lambda: os.environ.get("MICROSOFT_CLIENT_SECRET", ""))
    microsoft_tenant: str = field(default_factory=lambda: os.environ.get("MICROSOFT_TENANT", "organizations"))
    microsoft_allowed_tenants: list = field(default_factory=lambda: [t.lower() for t in _list("MICROSOFT_ALLOWED_TENANTS")])
    google_allowed_domains: list = field(default_factory=lambda: [d.lower() for d in _list("GOOGLE_ALLOWED_DOMAINS")])
    zoom_client_id: str = field(default_factory=lambda: os.environ.get("ZOOM_APP_CLIENT_ID", ""))
    zoom_client_secret: str = field(default_factory=lambda: os.environ.get("ZOOM_APP_CLIENT_SECRET", ""))
    zoom_secret_token: str = field(default_factory=lambda: os.environ.get("ZOOM_APP_SECRET_TOKEN", ""))

    @property
    def dev(self):
        return DEV

    @property
    def mail_enabled(self):
        return self.mail_backend == "smtp" and bool(self.smtp_host and self.mail_from)

    @property
    def turnstile_enabled(self):
        return bool(self.turnstile_site_key and self.turnstile_secret)

    def microsoft_tenants(self):
        if self.microsoft_allowed_tenants:
            return self.microsoft_allowed_tenants
        if self.microsoft_tenant.lower() not in ("common", "organizations", "consumers"):
            return [self.microsoft_tenant.lower()]
        return []

    def hosts(self):
        if self.allowed_hosts:
            return self.allowed_hosts
        if DEV:
            return []
        host = urllib.parse.urlsplit(self.public_url).netloc.lower()
        return [host] if host else []

    def validate(self):
        if len(self.secret_key) < 32:
            if DEV:
                self.secret_key = "dev-only-secret-key-change-me-0123456789abcdef"
            else:
                raise RuntimeError("SECRET_KEY must be set to at least 32 random characters "
                                   "(or set LIVE_MINUTES_DEV=1 for local development)")
        if self.mail_backend not in ("smtp", "console", "none"):
            raise RuntimeError("MAIL_BACKEND must be smtp, console or none")
        if self.mail_backend == "console" and not DEV:
            raise RuntimeError("MAIL_BACKEND=console prints sign-in links to the log; use it only with LIVE_MINUTES_DEV=1")
        if self.mail_backend == "smtp" and not (self.smtp_host and self.mail_from):
            raise RuntimeError("MAIL_BACKEND=smtp needs SMTP_HOST and MAIL_FROM")
        return self


settings = Settings()
