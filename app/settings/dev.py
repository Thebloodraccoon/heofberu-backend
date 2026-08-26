"""Dev-stage settings: async engine with SQL logging, open ALLOWED_HOSTS."""

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.settings._common import *  # noqa: F401, F403
from app.settings._common import (
    DATABASE_URL,
    REDIS_URL,
    as_async_database_url,
    make_async_session_factory,
    make_get_db,
    make_get_redis,
)

STAGE = "dev"
ALLOWED_HOSTS = ["*"]

engine = create_async_engine(
    as_async_database_url(DATABASE_URL),
    poolclass=pool.AsyncAdaptedQueuePool,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    pool_pre_ping=True,
    pool_timeout=30,
    echo=True,  # SQL logging on in dev
)

SessionLocal = make_async_session_factory(engine)
get_db = make_get_db(SessionLocal)
get_redis = make_get_redis(REDIS_URL)
