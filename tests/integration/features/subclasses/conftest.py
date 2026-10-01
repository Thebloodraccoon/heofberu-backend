"""Fixtures for the subclass integration tests."""

import pytest

from app.settings import settings


@pytest.fixture
def caching_on(monkeypatch, redis_client):
    """Turn the Redis cache on (the test stage keeps it off) with this process's keys cleaned up afterwards."""

    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    return redis_client
