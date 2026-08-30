"""Test-stage settings: isolated DB and Redis from env, non-echo async engine."""

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.settings._common import *  # noqa: F401, F403
from app.settings._common import (
    REDIS_URL,
    as_async_database_url,
    make_async_session_factory,
    make_get_db,
    make_get_redis,
)
from app.settings.config import AppSettings

_settings = AppSettings()

STAGE = "test"
ALLOWED_HOSTS = ["*"]

# Cache is off in tests by default so existing HTTP tests keep seeing
# fresh rows; enable it per-test with ``settings.CACHE_ENABLED = True``
# (the cache reads the flag at call time).
CACHE_ENABLED = False

# Test stage always targets the isolated TEST_* services, never the
# plain DATABASE_URL/REDIS_URL (which point at dev/prod).
DATABASE_URL = _settings.TEST_DATABASE_URL
REDIS_URL = _settings.TEST_REDIS_URL  # noqa: F811 -- deliberate override of the star-imported dev URL

engine = create_async_engine(
    as_async_database_url(DATABASE_URL),
    poolclass=pool.AsyncAdaptedQueuePool,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = make_async_session_factory(engine)
get_db = make_get_db(SessionLocal)
get_redis = make_get_redis(REDIS_URL)
