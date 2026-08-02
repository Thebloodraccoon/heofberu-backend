from contextlib import contextmanager

from redis import Redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.settings.base import Base  # noqa: F401
from app.settings.config import AppSettings

_settings = AppSettings()

APP_NAME = _settings.APP_NAME
APP_VERSION = _settings.APP_VERSION
STAGE = _settings.STAGE
HOST = _settings.HOST
ALLOWED_HOSTS = ["*"]

JWT_SECRET_KEY = _settings.JWT_SECRET_KEY
JWT_ALGORITHM = _settings.JWT_ALGORITHM

ADMIN_LOGIN = _settings.ADMIN_LOGIN
ADMIN_PASSWORD = _settings.ADMIN_PASSWORD

DATABASE_URL = _settings.DATABASE_URL
REDIS_URL = _settings.REDIS_URL

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    pool_pre_ping=True,
    pool_timeout=30,
    echo=False,
    future=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_redis():
    redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        yield redis_client
    finally:
        redis_client.close()
