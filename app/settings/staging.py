"""Staging-stage settings: same pool tuning as prod, ALLOWED_HOSTS from env.

Staging is the pre-production environment: it exercises the production
settings surface (docs disabled, strict host allow-list) while allowing
the host allow-list and pool to be tuned independently of prod if needed.
"""

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

STAGE = "staging"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")

# Payload & throughput limits — staging sits between dev and prod.
REQUEST_BODY_MAX_BYTES = 5 * 1024 * 1024
IMAGE_UPLOAD_MAX_BYTES = 2 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 20
MAX_CONCURRENT_CONNECTIONS_PER_IP = 30

engine = create_async_engine(
    as_async_database_url(DATABASE_URL),
    poolclass=pool.AsyncAdaptedQueuePool,
    pool_size=15,
    max_overflow=30,
    pool_recycle=1800,
    pool_pre_ping=True,
    pool_timeout=30,
    echo=False,
)

SessionLocal = make_async_session_factory(engine)
get_db = make_get_db(SessionLocal)
get_redis = make_get_redis(REDIS_URL)
