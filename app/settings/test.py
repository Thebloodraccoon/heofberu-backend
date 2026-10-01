"""Test-stage settings: isolated DB and Redis from env, non-echo async engine."""

from app.settings._common import *  # noqa: F401, F403
from app.settings._common import (
    make_async_session_factory,
    make_engine,
    make_get_db,
    make_get_redis,
)
from app.settings.config import AppSettings

_settings = AppSettings()

STAGE = "test"

# Off by default so HTTP tests see fresh rows; enable per test with ``settings.CACHE_ENABLED = True``
# (the cache reads the flag at call time).
CACHE_ENABLED = False

# The test stage always targets the isolated TEST_* services, never DATABASE_URL/REDIS_URL.
DATABASE_URL = _settings.TEST_DATABASE_URL
REDIS_URL = _settings.TEST_REDIS_URL  # noqa: F811
AUTH_REDIS_URL = REDIS_URL  # noqa: F811

engine = make_engine(DATABASE_URL, pool_size=5, max_overflow=10, pool_recycle=None)

SessionLocal = make_async_session_factory(engine)
get_db = make_get_db(SessionLocal)
get_redis = make_get_redis(REDIS_URL)
get_auth_redis = make_get_redis(AUTH_REDIS_URL)
