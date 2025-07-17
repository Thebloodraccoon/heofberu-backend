from pydantic_settings import BaseSettings


class MailSettings(BaseSettings):
    MAIL_SERVER: str
    MAIL_PORT: int
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str

    class Config:
        env_file = ".env"
        extra = "ignore"


mail_settings = MailSettings() # type: ignore[arg-type]
