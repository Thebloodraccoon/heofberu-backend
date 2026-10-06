"""Unit-test fixtures: no DB/Redis; pin the cache prefix so tests can assert literal ``cache:...`` keys."""

import pytest

from app.settings import settings


@pytest.fixture(autouse=True)
def _pin_cache_prefix(monkeypatch):
    # tests/isolation.py gives every process a unique CACHE_PREFIX for the shared real Redis;
    # unit tests use in-memory fakes, so the canonical prefix is safe here.
    monkeypatch.setattr(settings, "CACHE_PREFIX", "cache")
