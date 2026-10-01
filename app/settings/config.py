"""Pydantic settings model: loads and validates runtime configuration from the environment."""

import json
import logging
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

logger = logging.getLogger(__name__)

PROD_LIKE_STAGES = ("staging", "prod")

#: Placeholder secrets that must never run in a prod-like stage.
INSECURE_JWT_SECRETS = frozenset(
    {"", "secret", "your_jwt_secret_key", "changeme", "change-me", "change_me", "password"}
)

MIN_PROD_JWT_SECRET_LENGTH = 32

#: Default ``(pool_size, max_overflow, web_workers)`` per stage. ``workers * (pool + overflow)``
#: must stay below the Postgres ``max_connections`` (see ``DB_MAX_CONNECTIONS``).
STAGE_RUNTIME_DEFAULTS: dict[str, tuple[int, int, int]] = {
    "dev": (5, 10, 1),
    "test": (5, 10, 1),
    "staging": (5, 5, 2),
    "prod": (5, 5, 4),
}

#: Connections kept free for migrations, admin sessions and monitoring.
DB_RESERVED_CONNECTIONS = 10


def _csv(value):
    """Parse a comma separated (or JSON array) env value into a list of stripped strings."""

    if not isinstance(value, str):
        return value

    text = value.strip()
    if text.startswith("["):
        return [str(item).strip() for item in json.loads(text)]

    return [item.strip() for item in text.split(",") if item.strip()]


def _is_origin(value: str) -> bool:
    """Whether ``value`` is a bare ``http(s)://host[:port]`` origin."""

    parts = urlsplit(value)
    return parts.scheme in ("http", "https") and bool(parts.netloc) and not parts.path and not parts.query


class AppSettings(BaseSettings):
    """Application settings loaded from environment variables / ``.env`` file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    APP_NAME: str = "Heofberu Backend API"
    APP_VERSION: str = "1.0.0"
    STAGE: str = "dev"
    HOST: str = "0.0.0.0"  # nosec B104

    # JWT: dev/test may use the placeholder default; staging/prod must override it.
    JWT_SECRET_KEY: str = "secret"
    JWT_ALGORITHM: str = "HS256"

    # Used by the "default admin" guard (``ADMIN_LOGIN``); ADMIN_NAME/ADMIN_PASSWORD are read by migration 0003 only.
    ADMIN_LOGIN: str

    # Supabase file storage (core image-upload service).
    SUPABASE_URL: str
    SUPABASE_KEY: str
    STORAGE_BUCKET: str = "catalog-images"

    # Email (SMTP) for the password-reset mailer; prod must provide a reachable relay.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_STARTTLS: bool = False
    FRONTEND_RESET_URL: str = "https://heofberu-frontend.vercel.app/reset-password"

    DATABASE_URL: str
    REDIS_URL: str

    # Auth state (token blacklist, revocation marks, single-use claims) must never be evicted, so it lives on a
    # separate ``noeviction`` Redis. Empty = share ``REDIS_URL`` (dev/test only; staging/prod require a distinct one).
    AUTH_REDIS_URL: str = ""

    # Test DB & Redis (STAGE=test only).
    TEST_DATABASE_URL: str = ""
    TEST_REDIS_URL: str = ""

    # Browser origins (with scheme) allowed by CORS, and hostnames accepted in the Host header.
    # Comma separated. Dev/test default to "*"; staging/prod must list them explicitly.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=list)
    ALLOWED_HOSTS: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # Proxy addresses uvicorn trusts for X-Forwarded-For (comma separated IPs/CIDRs, or "*").
    # Required for rate limiting to see real client IPs behind a reverse proxy.
    FORWARDED_ALLOW_IPS: str = "127.0.0.1"

    # Cache: TTL is a safety net for missed invalidations; freshness comes from namespace purges.
    # CACHE_VERSION (e.g. a release id) is appended to the key prefix to retire old payload shapes.
    CACHE_ENABLED: bool = True
    CACHE_TTL_DEFAULT: int = 86400
    CACHE_PREFIX: str = "cache"
    CACHE_VERSION: str = ""
    CACHE_INDEX_MAX_KEYS: int = Field(default=50_000, ge=100)

    # DB pool sizing (per worker). ``None`` = stage default from ``STAGE_RUNTIME_DEFAULTS``.
    DB_POOL_SIZE: int | None = Field(default=None, ge=1)
    DB_MAX_OVERFLOW: int | None = Field(default=None, ge=0)
    WEB_CONCURRENCY: int | None = Field(default=None, ge=1)
    DB_MAX_CONNECTIONS: int = Field(default=100, ge=10)
    DB_COMMAND_TIMEOUT_SECONDS: int = Field(default=60, ge=0)

    REQUEST_BODY_MAX_BYTES: int = 5 * 1024 * 1024
    IMAGE_UPLOAD_MAX_BYTES: int = 5 * 1024 * 1024

    @field_validator("CORS_ORIGINS", "ALLOWED_HOSTS", mode="before")
    @classmethod
    def _split_list(cls, value):
        return _csv(value)

    @model_validator(mode="after")
    def _apply_stage_rules(self) -> "AppSettings":
        stage = self.STAGE.lower()

        pool, overflow, workers = STAGE_RUNTIME_DEFAULTS.get(stage, STAGE_RUNTIME_DEFAULTS["prod"])
        self.DB_POOL_SIZE = self.DB_POOL_SIZE if self.DB_POOL_SIZE is not None else pool
        self.DB_MAX_OVERFLOW = self.DB_MAX_OVERFLOW if self.DB_MAX_OVERFLOW is not None else overflow
        self.WEB_CONCURRENCY = self.WEB_CONCURRENCY if self.WEB_CONCURRENCY is not None else workers

        self.CORS_ORIGINS = [origin.rstrip("/") for origin in self.CORS_ORIGINS]

        if stage not in PROD_LIKE_STAGES:
            self.CORS_ORIGINS = self.CORS_ORIGINS or ["*"]
            self.ALLOWED_HOSTS = self.ALLOWED_HOSTS or ["*"]
            return self

        problems = [
            *self._jwt_problems(),
            *self._origin_problems(),
            *self._host_problems(),
            *self._pool_problems(),
            *self._auth_redis_problems(),
        ]
        if problems:
            raise ValueError(f"Invalid {stage!r} configuration: " + "; ".join(problems))

        if not (self.SMTP_HOST and self.SMTP_FROM):
            logger.warning("SMTP_HOST/SMTP_FROM are not set: password-reset emails will not be delivered")

        return self

    def _jwt_problems(self) -> list[str]:
        secret = self.JWT_SECRET_KEY
        if secret.strip().lower() in INSECURE_JWT_SECRETS:
            return ["JWT_SECRET_KEY must be overridden: a placeholder secret would let anyone forge tokens"]
        if len(secret) < MIN_PROD_JWT_SECRET_LENGTH:
            return [f"JWT_SECRET_KEY must be at least {MIN_PROD_JWT_SECRET_LENGTH} characters"]
        return []

    def _origin_problems(self) -> list[str]:
        if not self.CORS_ORIGINS:
            return ["CORS_ORIGINS must list the allowed browser origins (e.g. https://app.example.com)"]
        if "*" in self.CORS_ORIGINS:
            return ["CORS_ORIGINS must not contain a wildcard"]

        bad = [origin for origin in self.CORS_ORIGINS if not _is_origin(origin)]
        return [f"CORS_ORIGINS entries must be scheme://host[:port] without a path: {bad}"] if bad else []

    def _host_problems(self) -> list[str]:
        if not self.ALLOWED_HOSTS:
            return ["ALLOWED_HOSTS must list the accepted Host header names (e.g. api.example.com)"]
        if "*" in self.ALLOWED_HOSTS:
            return ["ALLOWED_HOSTS must not contain a wildcard"]

        bad = [host for host in self.ALLOWED_HOSTS if "://" in host or "/" in host]
        return [f"ALLOWED_HOSTS entries are bare host names, not URLs: {bad}"] if bad else []

    def _auth_redis_problems(self) -> list[str]:
        if not self.AUTH_REDIS_URL:
            return ["AUTH_REDIS_URL must point to a dedicated noeviction Redis so revocations cannot be evicted"]
        if self.AUTH_REDIS_URL == self.REDIS_URL:
            return ["AUTH_REDIS_URL must differ from REDIS_URL (the cache Redis evicts keys)"]
        return []

    def _pool_problems(self) -> list[str]:
        budget = self.DB_MAX_CONNECTIONS - DB_RESERVED_CONNECTIONS
        demand = self.WEB_CONCURRENCY * (self.DB_POOL_SIZE + self.DB_MAX_OVERFLOW)
        if demand > budget:
            return [
                f"WEB_CONCURRENCY x (DB_POOL_SIZE + DB_MAX_OVERFLOW) = {demand} exceeds the "
                f"connection budget {budget} (DB_MAX_CONNECTIONS - {DB_RESERVED_CONNECTIONS})"
            ]
        return []
