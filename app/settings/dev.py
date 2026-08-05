"""Dev-stage settings: engine with SQL logging, open ALLOWED_HOSTS."""

from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

from app.settings._common import *  # noqa: F401, F403
from app.settings._common import DATABASE_URL, REDIS_URL, make_get_db, make_get_redis, make_session_factory

STAGE = "dev"
ALLOWED_HOSTS = ["*"]

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    pool_pre_ping=True,
    pool_timeout=30,
    echo=True,  # SQL-лог включён в dev
    future=True,
)

SessionLocal = make_session_factory(engine)
get_db = make_get_db(SessionLocal)
get_redis = make_get_redis(REDIS_URL)