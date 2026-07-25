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

    # Postgres
    POSTGRES_USER: str = Field(default="postgres", alias="POSTGRES_USER")
    POSTGRES_PASSWORD: str = Field(default="postgres", alias="POSTGRES_PASSWORD")
    POSTGRES_HOST: str = Field(default="localhost", alias="POSTGRES_HOST")
    POSTGRES_PORT: int = Field(default=5432, alias="POSTGRES_PORT")
    POSTGRES_DB: str = Field(default="slavbor_db", alias="POSTGRES_DB")

    # Redis
    REDIS_HOST: str = Field(default="localhost", alias="REDIS_HOST")
    REDIS_PORT: int = Field(default=6379, alias="REDIS_PORT")
    REDIS_DB: int = Field(default=0, alias="REDIS_DB")

    @property
    def DATABASE_URL(self) -> str:  # noqa: N802
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )