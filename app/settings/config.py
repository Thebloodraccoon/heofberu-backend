from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    # App
    APP_NAME: str = "Heofberu Backend API"
    APP_VERSION: str = "1.0.0"
    STAGE: str = Field(default="local", alias="STAGE")
    HOST: str = "0.0.0.0"  # nosec B104

    # JWT
    JWT_SECRET_KEY: str = Field(default="secret", alias="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = Field(default="HS256", alias="JWT_ALGORITHM")

    # Admin — required, no silent None
    ADMIN_NAME: str = Field(..., alias="ADMIN_NAME")
    ADMIN_LOGIN: str = Field(..., alias="ADMIN_LOGIN")
    ADMIN_PASSWORD: str = Field(..., alias="ADMIN_PASSWORD")

    # DB & Redis URLs
    DATABASE_URL: str = Field(..., alias="DATABASE_URL")
    REDIS_URL: str = Field(..., alias="REDIS_URL")