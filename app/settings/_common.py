"""Shared settings logic: variables, session factory, and DB/Redis accessors."""

from contextlib import contextmanager

from redis import Redis
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.settings.base import Base  # noqa: F401
from app.settings.config import AppSettings

_settings = AppSettings()

APP_NAME = _settings.APP_NAME
APP_VERSION = _settings.APP_VERSION
STAGE = _settings.STAGE
HOST = _settings.HOST

JWT_SECRET_KEY = _settings.JWT_SECRET_KEY
JWT_ALGORITHM = _settings.JWT_ALGORITHM

ADMIN_NAME = _settings.ADMIN_NAME
ADMIN_LOGIN = _settings.ADMIN_LOGIN
ADMIN_PASSWORD = _settings.ADMIN_PASSWORD

DATABASE_URL = _settings.DATABASE_URL
REDIS_URL = _settings.REDIS_URL


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def make_get_db(session_factory: sessionmaker[Session]):
    """Returns a FastAPI dependency that yields a DB session."""

    def get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    return get_db


def make_get_redis(redis_url: str):
    """Returns a context manager that yields a connected Redis client."""

    @contextmanager
    def get_redis():
        client = Redis.from_url(redis_url, decode_responses=True)
        try:
            yield client
        finally:
            client.close()

    return get_redis