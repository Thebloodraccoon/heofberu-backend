"""Test-stage settings: isolated DB and Redis from env, non-echo QueuePool engine."""

from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

from app.settings._common import *  # noqa: F401, F403
from app.settings._common import make_get_db, make_get_redis, make_session_factory
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
REDIS_URL = _settings.TEST_REDIS_URL

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False,
    future=True,
)

SessionLocal = make_session_factory(engine)
get_db = make_get_db(SessionLocal)
get_redis = make_get_redis(REDIS_URL)
