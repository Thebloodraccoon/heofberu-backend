"""Pydantic settings model: loads runtime configuration from the environment."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application settings loaded from environment variables / ``.env`` file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    # App
    APP_NAME: str = "Heofberu Backend API"
    APP_VERSION: str = "1.0.0"
    STAGE: str = Field(default="dev", alias="STAGE")
    HOST: str = "0.0.0.0"  # nosec B104

    # JWT
    JWT_SECRET_KEY: str = Field(default="secret", alias="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = Field(default="HS256", alias="JWT_ALGORITHM")

    # Admin — required, no silent None
    ADMIN_NAME: str = Field(..., alias="ADMIN_NAME")
    ADMIN_LOGIN: str = Field(..., alias="ADMIN_LOGIN")
    ADMIN_PASSWORD: str = Field(..., alias="ADMIN_PASSWORD")

    # DB & Redis
    DATABASE_URL: str = Field(..., alias="DATABASE_URL")
    REDIS_URL: str = Field(..., alias="REDIS_URL")

    # Test DB & Redis (только для STAGE=test)
    TEST_DATABASE_URL: str = Field(default="", alias="TEST_DATABASE_URL")
    TEST_REDIS_URL: str = Field(default="", alias="TEST_REDIS_URL")

    # Cache (catalogs: spells/classes/races/feats/features/backgrounds/skills/items)
    # TTL - insurance in case of missed disability, freshness is provided by namespace reset.
    CACHE_ENABLED: bool = Field(default=True, alias="CACHE_ENABLED")
    CACHE_TTL_DEFAULT: int = Field(default=86400, alias="CACHE_TTL_DEFAULT")
    CACHE_PREFIX: str = Field(default="cache", alias="CACHE_PREFIX")
