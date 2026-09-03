"""
Shared settings logic: variables, session factory, and DB/Redis accessors.

Async stack: the engine/session layer is built on ``asyncpg`` +
``sqlalchemy.ext.asyncio``, and Redis access goes through ``redis.asyncio``.
"""

import asyncio
from contextlib import asynccontextmanager, suppress
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

SUPABASE_URL = _settings.SUPABASE_URL
SUPABASE_KEY = _settings.SUPABASE_KEY
STORAGE_BUCKET = _settings.STORAGE_BUCKET

SMTP_HOST = _settings.SMTP_HOST
SMTP_PORT = _settings.SMTP_PORT
SMTP_USER = _settings.SMTP_USER
SMTP_PASSWORD = _settings.SMTP_PASSWORD
SMTP_FROM = _settings.SMTP_FROM
SMTP_USE_TLS = _settings.SMTP_USE_TLS
SMTP_STARTTLS = _settings.SMTP_STARTTLS

DATABASE_URL = _settings.DATABASE_URL
REDIS_URL = _settings.REDIS_URL

CACHE_ENABLED = _settings.CACHE_ENABLED
CACHE_TTL_DEFAULT = _settings.CACHE_TTL_DEFAULT
CACHE_PREFIX = _settings.CACHE_PREFIX

# Request & payload limits (defaults; stages override tighter/looser values).
REQUEST_BODY_MAX_BYTES = _settings.REQUEST_BODY_MAX_BYTES
IMAGE_UPLOAD_MAX_BYTES = _settings.IMAGE_UPLOAD_MAX_BYTES
REQUEST_TIMEOUT_SECONDS = _settings.REQUEST_TIMEOUT_SECONDS
MAX_CONCURRENT_CONNECTIONS_PER_IP = _settings.MAX_CONCURRENT_CONNECTIONS_PER_IP


def utcnow() -> datetime:
    """Naive UTC "now", matching the DB's ``TIMESTAMP WITHOUT TIME ZONE`` columns."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_async_database_url(url: str) -> str:
    """
    Convert a sync ``postgresql://`` URL to the asyncpg driver form.

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
    """
    Returns an async context manager that yields a connected Redis client.

    The client is a lazy module-level singleton shared by every caller
    (cache reads/writes, JWT blacklist, rate limiting): one connection
    pool per process instead of a fresh TCP connect per operation. The
    yielded context manager does NOT close the client on exit.

    If the running event loop differs from the loop the singleton was
    created on (e.g. a new loop per test case), the client is rebuilt —
    redis-py connections are bound to the loop they first dialed on.
    """

    lock = asyncio.Lock()
    state: dict[str, object] = {"client": None, "loop": None}

    @asynccontextmanager
    async def get_redis():
        async with lock:
            current_loop = asyncio.get_running_loop()
            if state["client"] is None or state["loop"] is not current_loop:
                if state["client"] is not None:
                    # Best-effort close of a client bound to a dead event loop.
                    with suppress(Exception):
                        await state["client"].aclose()
                state["client"] = Redis.from_url(redis_url, decode_responses=True)
                state["loop"] = current_loop

        yield state["client"]

    return get_redis
