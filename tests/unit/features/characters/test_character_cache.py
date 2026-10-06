"""
Unit tests for character cache invalidation (app/features/characters/cache.py).

Exercised against ``FakeCacheRedis`` (same pattern as tests/unit/core): keys are
written through ``cache_set`` so they land in the namespace index, and
invalidation must remove exact keys without ever scanning the keyspace.
"""

from contextlib import asynccontextmanager

import pytest

from app.core.base.transaction import atomic
import app.core.cache.client as cache_client
from app.core.cache.client import cache_set
from app.features.characters.cache import (
    character_cache_key,
    invalidate_character_cache,
    invalidate_characters_cache,
)
from app.settings import settings
from tests.unit.fakes import FakeAsyncSession, FakeCacheRedis


@pytest.fixture
def fake_redis(monkeypatch):
    """Patch the Redis provider with a fresh ``FakeCacheRedis`` and enable caching."""
    store = FakeCacheRedis()

    @asynccontextmanager
    async def get_redis():
        yield store

    monkeypatch.setattr(cache_client, "_redis_provider", lambda: get_redis)
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    return store


@pytest.mark.unit
@pytest.mark.asyncio
class TestInvalidateCharactersCache:
    async def test_purges_the_response_key_of_every_given_character(self, fake_redis):
        for character_id in (1, 2, 3):
            await cache_set(character_cache_key(character_id), "x")
        await cache_set("cache:something_else:1", "keep")

        await invalidate_characters_cache([1, 2])

        assert set(fake_redis.data) == {character_cache_key(3), "cache:something_else:1"}

    async def test_never_scans_the_keyspace(self, fake_redis):
        await cache_set(character_cache_key(1), "a")

        await invalidate_characters_cache([1])
        await invalidate_character_cache(1)

        assert fake_redis.scans == 0

    async def test_uses_one_redis_connection_for_the_whole_batch(self, fake_redis, monkeypatch):
        opens = []
        real_provider = cache_client._redis_provider()

        @asynccontextmanager
        async def counting_get_redis():
            opens.append(1)
            async with real_provider() as redis:
                yield redis

        monkeypatch.setattr(cache_client, "_redis_provider", lambda: counting_get_redis)

        await invalidate_characters_cache([1, 2, 3])

        assert len(opens) == 1

    async def test_deduplicates_repeated_character_ids(self, fake_redis):
        await cache_set(character_cache_key(1), "a")

        await invalidate_characters_cache([1, 1, 1])

        assert fake_redis.data == {}
        assert fake_redis.unlinked == [character_cache_key(1)]

    async def test_empty_list_is_a_noop(self, fake_redis):
        await cache_set(character_cache_key(1), "a")

        await invalidate_characters_cache([])

        assert character_cache_key(1) in fake_redis.data
        assert fake_redis.unlinked == []

    async def test_redis_down_does_not_raise(self, fake_redis, monkeypatch):
        @asynccontextmanager
        async def broken_redis():
            raise ConnectionError("down")
            yield

        monkeypatch.setattr(cache_client, "_redis_provider", lambda: broken_redis)

        await invalidate_characters_cache([1, 2, 3])

    async def test_single_character_helper_removes_key_and_index_entry(self, fake_redis):
        await cache_set(character_cache_key(1), "a")
        await cache_set(character_cache_key(2), "b")

        await invalidate_character_cache(1)

        assert set(fake_redis.data) == {character_cache_key(2)}
        assert character_cache_key(1) not in set().union(*fake_redis.sets.values())

    async def test_key_matches_the_flat_detail_key_format(self):
        assert character_cache_key(7) == f"{settings.CACHE_PREFIX}:characters:7"


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeferredInvalidation:
    async def test_purge_waits_for_the_commit_inside_an_atomic_block(self, fake_redis):
        await cache_set(character_cache_key(1), "a")
        db = FakeAsyncSession()

        async with atomic(db):
            await invalidate_character_cache(1, db=db)
            assert character_cache_key(1) in fake_redis.data

        assert fake_redis.data == {}

    async def test_batch_purge_waits_for_the_commit_too(self, fake_redis):
        await cache_set(character_cache_key(1), "a")
        await cache_set(character_cache_key(2), "b")
        db = FakeAsyncSession()

        async with atomic(db):
            await invalidate_characters_cache([1, 2], db=db)
            assert len(fake_redis.data) == 2

        assert fake_redis.data == {}

    async def test_rollback_drops_the_purge(self, fake_redis):
        await cache_set(character_cache_key(1), "a")
        db = FakeAsyncSession()

        with pytest.raises(RuntimeError):
            async with atomic(db):
                await invalidate_character_cache(1, db=db)
                raise RuntimeError("boom")

        assert character_cache_key(1) in fake_redis.data

    async def test_outside_a_transaction_the_purge_is_immediate(self, fake_redis):
        await cache_set(character_cache_key(1), "a")

        await invalidate_character_cache(1, db=FakeAsyncSession())

        assert fake_redis.data == {}
