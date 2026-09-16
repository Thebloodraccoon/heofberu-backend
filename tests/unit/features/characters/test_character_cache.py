"""
Unit tests for character cache invalidation (app/features/characters/cache.py).

Exercised against a fake Redis store (same pattern as
tests/unit/core/test_cache_decorator.py) so the batched
``invalidate_characters_cache`` path is verified against real key names,
not just call counts on a mock.
"""

from contextlib import asynccontextmanager
import fnmatch

import pytest

import app.core.cache.client as cache_client
from app.features.characters.cache import invalidate_character_cache, invalidate_characters_cache
from app.settings import settings


class FakeRedis:
    """Minimal in-memory stand-in for the async Redis surface the cache uses."""

    def __init__(self):
        self.data = {}
        self.delete_calls = []

    async def scan_iter(self, match=None, count=100):
        keys = list(self.data)
        if match is not None:
            keys = [key for key in keys if fnmatch.fnmatchcase(key, match)]
        for key in keys:
            yield key

    async def delete(self, *keys):
        self.delete_calls.append(set(keys))
        removed = 0
        for key in keys:
            if self.data.pop(key, None) is not None:
                removed += 1
        return removed


@pytest.fixture
def fake_redis(monkeypatch):
    """Patch the Redis provider with a fresh ``FakeRedis`` and enable caching."""
    store = FakeRedis()

    @asynccontextmanager
    async def get_redis():
        yield store

    monkeypatch.setattr(cache_client, "_redis_provider", lambda: get_redis)
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    return store


@pytest.mark.unit
@pytest.mark.asyncio
class TestInvalidateCharactersCache:
    async def test_purges_every_key_for_every_given_character(self, fake_redis):
        fake_redis.data = {
            "cache:characters:1": "a",
            "cache:characters:1:stats": "b",
            "cache:characters:2": "c",
            "cache:characters:3": "d",
            "cache:something_else": "keep",
        }

        await invalidate_characters_cache([1, 2])

        assert fake_redis.data == {"cache:characters:3": "d", "cache:something_else": "keep"}

    async def test_uses_one_redis_connection_for_the_whole_batch(self, fake_redis, monkeypatch):
        opens = []
        real_provider = cache_client._redis_provider()

        @asynccontextmanager
        async def counting_get_redis():
            opens.append(1)
            async with real_provider() as redis:
                yield redis

        monkeypatch.setattr(cache_client, "_redis_provider", lambda: counting_get_redis)
        fake_redis.data = {"cache:characters:1": "a", "cache:characters:2": "b"}

        await invalidate_characters_cache([1, 2])

        assert len(opens) == 1

    async def test_deduplicates_repeated_character_ids(self, fake_redis):
        fake_redis.data = {"cache:characters:1": "a"}

        await invalidate_characters_cache([1, 1, 1])

        assert fake_redis.data == {}
        assert fake_redis.delete_calls == [{"cache:characters:1"}]

    async def test_empty_list_is_a_noop(self, fake_redis):
        fake_redis.data = {"cache:characters:1": "a"}

        await invalidate_characters_cache([])

        assert fake_redis.data == {"cache:characters:1": "a"}
        assert fake_redis.delete_calls == []

    async def test_redis_down_does_not_raise(self, fake_redis, monkeypatch):
        @asynccontextmanager
        async def broken_redis():
            raise ConnectionError("down")
            yield

        monkeypatch.setattr(cache_client, "_redis_provider", lambda: broken_redis)

        await invalidate_characters_cache([1, 2, 3])

    async def test_matches_single_character_helper_for_one_id(self, fake_redis):
        """invalidate_characters_cache([id]) purges the same keys invalidate_character_cache(id) would."""
        fake_redis.data = {
            "cache:characters:1": "a",
            "cache:characters:1:nested": "b",
            "cache:characters:2": "c",
        }

        await invalidate_characters_cache([1])

        assert fake_redis.data == {"cache:characters:2": "c"}

    async def test_single_character_helper_still_works_standalone(self, fake_redis):
        fake_redis.data = {"cache:characters:1": "a", "cache:characters:1:nested": "b"}

        await invalidate_character_cache(1)

        assert fake_redis.data == {}
