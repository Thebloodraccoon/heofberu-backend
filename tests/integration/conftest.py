"""
Integration-test fixtures: schema via Alembic, DB session, and Redis.

These are deliberately scoped to ``tests/integration``: they require the
``heof-test-db`` / ``heof-test-redis`` containers from ``docker-compose.dev.yml``.
Unit tests never import this module, so they stay fast and DB-free.
"""

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
import pytest  # noqa: E402
from redis import Redis  # noqa: E402

from app.settings import settings  # noqa: E402

ALEMBIC_INI = "alembic.ini"


def _run_migrations() -> None:
    """Apply all Alembic migrations to the test database."""
    cfg = Config(ALEMBIC_INI)
    command.upgrade(cfg, "head")


def _truncate_all_tables(session) -> None:
    """Delete all rows in child-first order so FK constraints are respected."""
    for table in reversed(settings.Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()


@pytest.fixture(scope="session")
def prepare_database():
    """
    Create the test schema via Alembic once per session.

    Not autouse: only pulled in by fixtures that touch the database
    (``db_session``), so unit tests never need the test DB to be running.
    """
    _run_migrations()
    yield
    settings.engine.dispose()


@pytest.fixture
def db_session(prepare_database):
    """A fresh, truncated DB session per test."""
    session = settings.SessionLocal()
    try:
        _truncate_all_tables(session)
        yield session
    finally:
        session.close()


@pytest.fixture
def redis_client():
    """A connected, flushed Redis client for the test DB."""
    client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()
    client.close()
