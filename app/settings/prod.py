"""Production-stage settings: tuned async pool, ALLOWED_HOSTS from env."""

import os

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

STAGE = "prod"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")

engine = create_async_engine(
    as_async_database_url(DATABASE_URL),
    poolclass=pool.AsyncAdaptedQueuePool,
    pool_size=20,
    max_overflow=40,
    pool_recycle=1800,
    pool_pre_ping=True,
    pool_timeout=30,
    echo=False,  # SQL logging off in prod
)

SessionLocal = make_async_session_factory(engine)
get_db = make_get_db(SessionLocal)
get_redis = make_get_redis(REDIS_URL)
