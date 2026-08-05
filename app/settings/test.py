"""Test-stage settings: StaticPool, isolated DB and Redis from env."""

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.settings._common import *  # noqa: F401, F403
from app.settings._common import make_get_db, make_get_redis, make_session_factory
from app.settings.config import AppSettings

_settings = AppSettings()

STAGE = "test"
ALLOWED_HOSTS = ["*"]

DATABASE_URL = _settings.TEST_DATABASE_URL
REDIS_URL = _settings.TEST_REDIS_URL

engine = create_engine(
    DATABASE_URL,
    poolclass=StaticPool,
    connect_args={"check_same_thread": False},
    echo=False,
    future=True,
)

SessionLocal = make_session_factory(engine)
get_db = make_get_db(SessionLocal)
get_redis = make_get_redis(REDIS_URL)