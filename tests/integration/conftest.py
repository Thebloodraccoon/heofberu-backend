"""
Integration-test fixtures: per-process database (Alembic template), async DB session, Redis.

These are deliberately scoped to ``tests/integration``: they require the
``heof-test-db`` / ``heof-test-redis`` containers from ``docker-compose.dev.yml``.
Unit tests never import this module, so they stay fast and DB-free.

The DB session is an ``AsyncSession`` (the app runs on the asyncio stack);
Redis access goes through ``redis.asyncio``. Migrations run synchronously
via Alembic (``migrations/env.py`` stays sync, driving psycopg2).
"""

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from redis.asyncio import Redis  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.settings import settings  # noqa: E402
from tests import isolation  # noqa: E402


async def _truncate_all_tables(session) -> None:
    """
    Wipe every table in one atomic TRUNCATE ... CASCADE statement.

    A single TRUNCATE (instead of per-table DELETEs) cannot hit FK-ordering
    issues, is far faster on big catalogs, and — crucially — is all-or-nothing:
    a partial wipe can never leave stale rows that poison later tests with
    unique-constraint violations.
    """

    await session.rollback()  # discard any aborted/stale transaction state
    table_names = ", ".join(f'"{table.name}"' for table in settings.Base.metadata.sorted_tables)
    await session.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))

    await session.commit()


@pytest.fixture(scope="session")
def prepare_database():
    """
    Create this process's own database (``heof_test_<run>_<worker>``) once per session.

    The DB is cloned from a migrated template (built once per migration set by
    Alembic under a cross-process Postgres advisory lock) and dropped at session
    end, also when tests fail. Sync on purpose: session-scoped and independent of
    function event loops. Not autouse: only ``db_session`` pulls it in, so unit
    tests never need Postgres.
    """

    isolation.create_worker_database()
    try:
        yield
    finally:
        isolation.drop_worker_database()


@pytest_asyncio.fixture
async def db_session(prepare_database):
    """A fresh, truncated async DB session per test (on this process's own database)."""

    session = settings.SessionLocal()
    try:
        await _truncate_all_tables(session)
        yield session
    finally:
        await session.close()


@pytest_asyncio.fixture
async def redis_client():
    """
    A connected Redis client with this process's key namespace cleared before/after.

    Never ``flushdb``: Redis is shared with other runs/workers. Only keys under
    ``settings.CACHE_PREFIX`` and this process's rate-limit buckets are deleted.
    """

    client = Redis.from_url(settings.REDIS_URL, decode_responses=True)

    await isolation.clear_redis_keys(client)
    yield client
    await isolation.clear_redis_keys(client)

    await client.aclose()
