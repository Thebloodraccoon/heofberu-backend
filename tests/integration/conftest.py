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

_TABLE_NAMES = None
_NON_EMPTY_SQL = None


def _table_names() -> list[str]:
    global _TABLE_NAMES, _NON_EMPTY_SQL
    if _TABLE_NAMES is None:
        _TABLE_NAMES = [table.name for table in settings.Base.metadata.sorted_tables]
        _NON_EMPTY_SQL = " UNION ALL ".join(
            f"SELECT '{name}' WHERE EXISTS (SELECT 1 FROM \"{name}\")" for name in _TABLE_NAMES
        )
    return _TABLE_NAMES


async def _truncate_all_tables(session) -> None:
    """
    Full wipe in one atomic TRUNCATE ... CASCADE (slow: ~1 s for ~60 tables on the test server,
    because every table gets a new relfilenode). Kept as the safe fallback and for the first test.
    """

    await session.rollback()  # discard any aborted/stale transaction state
    table_names = ", ".join(f'"{name}"' for name in _table_names())
    await session.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))

    await session.commit()


async def _reset_database(session) -> None:
    """
    Return the DB to the empty, identity-reset state cheaply: only touched tables are cleaned.

    One probe query finds non-empty tables and used sequences; those get a plain DELETE (FK
    triggers disabled for the transaction via ``session_replication_role=replica`` -- every
    non-empty table is wiped, so no dangling rows remain) and ``ALTER SEQUENCE ... RESTART``.
    Equivalent to ``TRUNCATE ... RESTART IDENTITY`` but ~10-30x faster for a typical test that
    touches a handful of tables. Falls back to the full TRUNCATE if anything unexpected happens
    (e.g. a role without the privilege to change ``session_replication_role``).
    """

    await session.rollback()
    _table_names()
    try:
        dirty = [row[0] for row in (await session.execute(text(_NON_EMPTY_SQL))).all()]
        sequences = [
            row[0]
            for row in (
                await session.execute(
                    text(
                        "SELECT sequencename FROM pg_sequences WHERE schemaname = current_schema() AND last_value IS NOT NULL"
                    )
                )
            ).all()
        ]
        if not dirty and not sequences:
            await session.rollback()
            return
        if dirty:
            await session.execute(text("SET LOCAL session_replication_role = replica"))
            for name in dirty:
                await session.execute(text(f'DELETE FROM "{name}"'))
        for name in sequences:
            await session.execute(text(f'ALTER SEQUENCE "{name}" RESTART'))
        await session.commit()
    except Exception:
        await _truncate_all_tables(session)


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
        await _reset_database(session)
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
