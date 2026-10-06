"""Dev-stage settings: SQL echo on, permissive CORS/hosts, large body limit."""

from app.settings._common import *  # noqa: F401, F403
from app.settings._common import (
    AUTH_REDIS_URL,
    DATABASE_URL,
    DB_MAX_OVERFLOW,
    DB_POOL_SIZE,
    REDIS_URL,
    _settings,
    make_async_session_factory,
    make_engine,
    make_get_db,
    make_get_redis,
)

STAGE = "dev"

REQUEST_BODY_MAX_BYTES = 10 * 1024 * 1024
IMAGE_UPLOAD_MAX_BYTES = 5 * 1024 * 1024

engine = make_engine(
    DATABASE_URL,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_recycle=3600,
    echo=True,
    command_timeout=_settings.DB_COMMAND_TIMEOUT_SECONDS,
)

SessionLocal = make_async_session_factory(engine)
get_db = make_get_db(SessionLocal)
get_redis = make_get_redis(REDIS_URL)
get_auth_redis = make_get_redis(AUTH_REDIS_URL)
