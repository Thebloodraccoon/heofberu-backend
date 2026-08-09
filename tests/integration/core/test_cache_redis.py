"""Integration tests for the Redis-backed cache against the real test Redis.

Requires the ``heof-test-redis`` container (``docker-compose.dev.yml``).
The ``redis_client`` fixture (from ``tests/integration/conftest.py``) flushes
the database before and after every test. ``CACHE_ENABLED`` is flipped on
per-test because the test stage keeps it off by default.
"""

import pytest
from pydantic import BaseModel

from app.core.cache import invalidate, use_cache
from app.core.cache.client import cache_delete_prefix, cache_get, cache_set
from app.settings import settings

KEY = "cache:test:key"


@pytest.fixture
def caching_on(monkeypatch):
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "CACHE_TTL_DEFAULT", 300)


class Quote(BaseModel):
    text: str
    author: str


class Quotes:
    cache_namespaces = ("quotes",)

    def __init__(self):
        self.calls = 0

    @use_cache()
    def get(self, slug: str = "top") -> Quote:
        self.calls += 1
        return Quote(text="hello", author="me")


@pytest.mark.integration
class TestCacheStore:
    def test_set_get_roundtrip(self, redis_client, caching_on):
        cache_set(KEY, "value", ttl=60)

        assert cache_get(KEY) == "value"
        assert redis_client.ttl(KEY) > 0

    def test_set_without_ttl_uses_default(self, redis_client, caching_on):
        cache_set(KEY, "value")

        assert cache_get(KEY) == "value"
        assert redis_client.ttl(KEY) == settings.CACHE_TTL_DEFAULT

    def test_missing_key_is_none(self, redis_client, caching_on):
        assert cache_get("cache:missing:*") is None

    def test_delete_prefix_removes_only_namespace(self, redis_client, caching_on):
        cache_set("cache:spells:get_all:1=1", "a")
        cache_set("cache:spells:get_by_id:1", "b")
        cache_set("cache:other:get:1=1", "c")

        cache_delete_prefix("spells")

        assert cache_get("cache:spells:get_all:1=1") is None
        assert cache_get("cache:spells:get_by_id:1") is None
        assert cache_get("cache:other:get:1=1") == "c"

    def test_invalidate_shortcut(self, redis_client, caching_on):
        cache_set("cache:items:get_all:1=1", "a")

        invalidate("items")

        assert cache_get("cache:items:get_all:1=1") is None

    def test_decorator_shares_cache_across_instances(self, redis_client, caching_on):
        first = Quotes()
        second = Quotes()

        assert first.get("top") == second.get("top")

        assert first.calls == 1
        assert second.calls == 0

    def test_decorator_honours_disabled_cache(self, redis_client, caching_on, monkeypatch):
        monkeypatch.setattr(settings, "CACHE_ENABLED", False)
        first = Quotes()

        first.get("top")
        first.get("top")

        assert first.calls == 2
