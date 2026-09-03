"""Pydantic settings model: loads runtime configuration from the environment."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application settings loaded from environment variables / ``.env`` file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    # App
    APP_NAME: str = "Heofberu Backend API"
    APP_VERSION: str = "1.0.0"
    STAGE: str = Field(default="dev", alias="STAGE")
    HOST: str = "0.0.0.0"  # nosec B104

    # JWT — dev/test may fall back to a well-known default; prod must not.
    JWT_SECRET_KEY: str = Field(default="secret", alias="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = Field(default="HS256", alias="JWT_ALGORITHM")

    # Admin — required, no silent None
    ADMIN_NAME: str = Field(..., alias="ADMIN_NAME")
    ADMIN_LOGIN: str = Field(..., alias="ADMIN_LOGIN")
    ADMIN_PASSWORD: str = Field(..., alias="ADMIN_PASSWORD")

    # Supabase file storage — used by the core image-upload service
    SUPABASE_URL: str = Field(..., alias="SUPABASE_URL")
    SUPABASE_KEY: str = Field(..., alias="SUPABASE_KEY")
    STORAGE_BUCKET: str = Field(default="catalog-images", alias="STORAGE_BUCKET")

    # Email (SMTP) — used by the password-reset mailer. No defaults in prod:
    # production is required to provide a reachable SMTP relay.
    SMTP_HOST: str = Field(default="", alias="SMTP_HOST")
    SMTP_PORT: int = Field(default=587, alias="SMTP_PORT")
    SMTP_USER: str = Field(default="", alias="SMTP_USER")
    SMTP_PASSWORD: str = Field(default="", alias="SMTP_PASSWORD")
    SMTP_FROM: str = Field(default="", alias="SMTP_FROM")
    SMTP_USE_TLS: bool = Field(default=True, alias="SMTP_USE_TLS")
    SMTP_STARTTLS: bool = Field(default=False, alias="SMTP_STARTTLS")

    # DB & Redis
    DATABASE_URL: str = Field(..., alias="DATABASE_URL")
    REDIS_URL: str = Field(..., alias="REDIS_URL")

    # Test DB & Redis (STAGE=test only)
    TEST_DATABASE_URL: str = Field(default="", alias="TEST_DATABASE_URL")
    TEST_REDIS_URL: str = Field(default="", alias="TEST_REDIS_URL")

    # Cache (catalogs: spells/classes/races/feats/features/backgrounds/skills/items).
    # TTL is a safety net for missed invalidations; freshness comes from namespace purges.
    CACHE_ENABLED: bool = Field(default=True, alias="CACHE_ENABLED")
    CACHE_TTL_DEFAULT: int = Field(default=86400, alias="CACHE_TTL_DEFAULT")
    CACHE_PREFIX: str = Field(default="cache", alias="CACHE_PREFIX")

    # Request & payload limits (bytes / seconds / connections).
    # Favors more permissive defaults; individual stages override tighter ones.
    REQUEST_BODY_MAX_BYTES: int = Field(default=5 * 1024 * 1024, alias="REQUEST_BODY_MAX_BYTES")
    IMAGE_UPLOAD_MAX_BYTES: int = Field(default=5 * 1024 * 1024, alias="IMAGE_UPLOAD_MAX_BYTES")
    REQUEST_TIMEOUT_SECONDS: int = Field(default=30, alias="REQUEST_TIMEOUT_SECONDS")

    # Enforced at the reverse proxy/server level (nginx/uvicorn), documented
    # here so each stage can tune the cap independently.
    MAX_CONCURRENT_CONNECTIONS_PER_IP: int = Field(default=50, alias="MAX_CONCURRENT_CONNECTIONS_PER_IP")

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def reject_default_secret_outside_dev(cls, value: str, info) -> str:
        """Fail startup when a non-dev stage runs with the placeholder secret."""

        stage = info.data.get("STAGE", "dev")
        if value == "secret" and stage not in ("dev", "test"):
            raise ValueError(
                "JWT_SECRET_KEY must be overridden outside dev/test — the default "
                "'secret' would let anyone forge tokens."
            )
        return value
