"""
Integration-test fixtures: schema via Alembic, async DB session, and Redis.

These are deliberately scoped to ``tests/integration``: they require the
``heof-test-db`` / ``heof-test-redis`` containers from ``docker-compose.dev.yml``.
Unit tests never import this module, so they stay fast and DB-free.

The DB session is an ``AsyncSession`` (the app runs on the asyncio stack);
Redis access goes through ``redis.asyncio``. Migrations run synchronously
via Alembic (``migrations/env.py`` stays sync, driving psycopg2).
"""

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from redis.asyncio import Redis  # noqa: E402

from app.settings import settings  # noqa: E402

ALEMBIC_INI = "alembic.ini"


def _run_migrations() -> None:
    """Apply all Alembic migrations to the test database."""
    cfg = Config(ALEMBIC_INI)
    command.upgrade(cfg, "head")


async def _truncate_all_tables(session) -> None:
    """Delete all rows in child-first order so FK constraints are respected."""
    for table in reversed(settings.Base.metadata.sorted_tables):
        await session.execute(table.delete())
    await session.commit()


@pytest.fixture(scope="session")
def prepare_database():
    """
    Create the test schema via Alembic once per session.

    Deliberately sync: the session-scoped fixture cannot depend on a
    function-scoped asyncio event loop, and Alembic's migration runner
    (``migrations/env.py``) is synchronous. The async engine is left for
    process-exit cleanup — calling ``engine.dispose()`` from a different
    event loop would break asyncpg pool connections.

    Not autouse: only pulled in by fixtures that touch the database
    (``db_session``), so unit tests never need the test DB to be running.
    """
    _run_migrations()
    yield


@pytest_asyncio.fixture
async def db_session(prepare_database):
    """A fresh, truncated async DB session per test."""
    session = settings.SessionLocal()
    try:
        await _truncate_all_tables(session)
        yield session
    finally:
        await session.close()


@pytest_asyncio.fixture
async def redis_client():
    """A connected, flushed Redis client for the test DB."""
    client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()
