"""Integration tests for index-based namespace invalidation against the real test Redis."""

from pydantic import BaseModel
import pytest

from app.core.cache import invalidate, invalidate_many, use_cache
import app.core.cache.client as cache_client
from app.core.cache.client import cache_delete_key, cache_epoch, cache_flush_all, cache_get, cache_set
from app.settings import settings

P = settings.CACHE_PREFIX  # per-process prefix (tests/isolation.py)


@pytest.fixture
def caching_on(monkeypatch):
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "CACHE_TTL_DEFAULT", 300)


class Row(BaseModel):
    id: int


class Rows:
    cache_namespaces = ("rows",)

    def __init__(self):
        self.calls = 0

    @use_cache()
    def get_by_id(self, item_id: int) -> Row:
        self.calls += 1
        return Row(id=item_id)


@pytest.mark.integration
@pytest.mark.asyncio
class TestIndexedInvalidation:
    async def test_cache_set_indexes_the_key_and_the_index_has_no_ttl(self, redis_client, caching_on):
        await cache_set(f"{P}:spells:get_all:1=1", "a", ttl=60)

        assert await redis_client.smembers(f"{P}:__idx:spells") == {f"{P}:spells:get_all:1=1"}
        assert await redis_client.ttl(f"{P}:__idx:spells") == -1
        assert 0 < await redis_client.ttl(f"{P}:spells:get_all:1=1") <= 60

    async def test_an_index_that_had_a_ttl_loses_it_on_the_next_write(self, redis_client, caching_on):
        await redis_client.sadd(f"{P}:__idx:spells", "x")
        await redis_client.expire(f"{P}:__idx:spells", 1000)

        await cache_set(f"{P}:spells:get_all:1=1", "a")

        assert await redis_client.ttl(f"{P}:__idx:spells") == -1

    async def test_invalidate_removes_namespace_keys_and_the_index(self, redis_client, caching_on):
        await cache_set(f"{P}:spells:get_all:1=1", "a")
        await cache_set(f"{P}:spells:get_by_id:1=5", "b")
        await cache_set(f"{P}:other:get", "c")

        await invalidate("spells")

        assert await cache_get(f"{P}:spells:get_all:1=1") is None
        assert await cache_get(f"{P}:spells:get_by_id:1=5") is None
        assert await cache_get(f"{P}:other:get") == "c"
        assert await redis_client.exists(f"{P}:__idx:spells") == 0

    async def test_second_level_namespace_and_flat_key(self, redis_client, caching_on):
        await cache_set(f"{P}:characters:1", "flat")
        await cache_set(f"{P}:characters:1:stats", "a")
        await cache_set(f"{P}:characters:2:stats", "b")

        await invalidate("characters:1")
        await cache_delete_key(f"{P}:characters:1")

        assert await cache_get(f"{P}:characters:1:stats") is None
        assert await cache_get(f"{P}:characters:1") is None
        assert await cache_get(f"{P}:characters:2:stats") == "b"
        assert f"{P}:characters:1:stats" not in await redis_client.smembers(f"{P}:__idx:characters")

    async def test_invalidate_many_in_one_call(self, redis_client, caching_on):
        await cache_set(f"{P}:a:get", "1")
        await cache_set(f"{P}:b:get", "2")
        await cache_set(f"{P}:c:get", "3")

        await invalidate_many(["a", "b"], [f"{P}:c:get"])

        assert [await cache_get(f"{P}:{name}:get") for name in "abc"] == [None, None, None]

    async def test_decorated_reads_refill_after_invalidation(self, redis_client, caching_on):
        service = Rows()

        await service.get_by_id(1)
        await service.get_by_id(item_id=1)
        assert service.calls == 1

        await invalidate("rows")
        await service.get_by_id(1)

        assert service.calls == 2

    async def test_flush_all_keeps_non_cache_keys(self, redis_client, caching_on):
        await cache_set(f"{P}:a:get", "1")
        await redis_client.set(f"token_blacklist:{P}", "x", ex=60)

        await cache_flush_all()

        assert await cache_get(f"{P}:a:get") is None
        assert await redis_client.exists(f"{P}:__idx:a") == 0
        assert await redis_client.get(f"token_blacklist:{P}") == "x"
        await redis_client.delete(f"token_blacklist:{P}")


@pytest.mark.integration
@pytest.mark.asyncio
class TestEpochAndRecovery:
    async def test_every_purge_and_flush_bumps_the_epoch_and_flush_keeps_the_counter(self, redis_client, caching_on):
        start = int(await cache_epoch() or 0)

        await invalidate("spells")
        await cache_delete_key(f"{P}:a:1")
        await cache_flush_all()

        assert int(await cache_epoch()) == start + 3

    async def test_refill_computed_before_a_purge_is_discarded(self, redis_client, caching_on):
        epoch = await cache_epoch()

        await invalidate("spells")
        await cache_set(f"{P}:spells:get_by_id:1=5", "stale", epoch=epoch)

        assert await cache_get(f"{P}:spells:get_by_id:1=5") is None
        assert await redis_client.smembers(f"{P}:__idx:spells") == set()

    async def test_decorated_read_racing_a_purge_stays_uncached(self, redis_client, caching_on):
        class Racing:
            cache_namespaces = ("racing",)

            def __init__(self):
                self.first = True

            @use_cache()
            async def get(self, item_id: int) -> Row:
                if self.first:
                    self.first = False
                    await invalidate("racing")
                return Row(id=item_id)

        service = Racing()
        await service.get(1)

        assert await redis_client.keys(f"{P}:racing:*") == []
        await service.get(1)
        assert await redis_client.keys(f"{P}:racing:*") != []

    async def test_purge_that_failed_against_real_redis_is_replayed_on_recovery(
        self, redis_client, caching_on, monkeypatch
    ):
        from contextlib import asynccontextmanager

        real_provider = settings.get_redis
        state = {"down": False}

        @asynccontextmanager
        async def flaky():
            if state["down"]:
                raise ConnectionError("down")
            async with real_provider() as redis:
                yield redis

        monkeypatch.setattr(cache_client, "_redis_provider", lambda: flaky)
        await cache_set(f"{P}:spells:get_by_id:1=5", "stale")

        state["down"] = True
        await invalidate("spells")
        state["down"] = False
        cache_client._breaker.success()

        assert await cache_get(f"{P}:spells:get_by_id:1=5") is None
        assert await redis_client.exists(f"{P}:spells:get_by_id:1=5") == 0
        assert not cache_client._pending
