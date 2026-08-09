"""Shared settings logic: variables, session factory, and DB/Redis accessors.

Async stack: the engine/session layer is built on ``asyncpg`` +
``sqlalchemy.ext.asyncio``, and Redis access goes through ``redis.asyncio``.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

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

CACHE_ENABLED = _settings.CACHE_ENABLED
CACHE_TTL_DEFAULT = _settings.CACHE_TTL_DEFAULT
CACHE_PREFIX = _settings.CACHE_PREFIX


def utcnow() -> datetime:
    """Naive UTC "now", matching the DB's ``TIMESTAMP WITHOUT TIME ZONE`` columns."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_async_database_url(url: str) -> str:
    """Convert a sync ``postgresql://`` URL to the asyncpg driver form.

    Query params that asyncpg does not accept (``sslmode``, ``channel_binding``)
    are stripped from the URL; ``sslmode`` is translated to asyncpg's ``ssl``.
    Example: ``...?sslmode=require&channel_binding=require`` ->
    ``...?ssl=require``.
    """

    if "+asyncpg" not in url:
        url = url.replace("postgres://", "postgresql://")
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    parts = urlsplit(url)
    if not parts.query:
        return url

    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)
    if sslmode:
        query["ssl"] = sslmode

    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def make_async_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def make_get_db(session_factory: async_sessionmaker[AsyncSession]):
    """Returns a FastAPI dependency that yields an async DB session."""

    async def get_db():
        db = session_factory()
        try:
            yield db
        finally:
            await db.close()

    return get_db


def make_get_redis(redis_url: str):
    """Returns an async context manager that yields a connected Redis client."""

    @asynccontextmanager
    async def get_redis():
        client = Redis.from_url(redis_url, decode_responses=True)
        try:
            yield client
        finally:
            await client.aclose()

    return get_redis
