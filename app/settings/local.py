from contextlib import asynccontextmanager

from redis.asyncio import Redis
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

POSTGRES_USER = _settings.POSTGRES_USER
POSTGRES_PASSWORD = _settings.POSTGRES_PASSWORD
POSTGRES_HOST = _settings.POSTGRES_HOST
POSTGRES_PORT = _settings.POSTGRES_PORT
POSTGRES_DB = _settings.POSTGRES_DB
DATABASE_URL = _settings.DATABASE_URL

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


# Redis
REDIS_HOST = _settings.REDIS_HOST
REDIS_PORT = _settings.REDIS_PORT
REDIS_DB = _settings.REDIS_DB


@asynccontextmanager
async def get_redis():
    redis_client = Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
    )
    try:
        yield redis_client
    finally:
        await redis_client.aclose()
