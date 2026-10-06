"""Unit tests for the cache store: namespace key indexes, invalidation without SCAN, circuit breaker."""

from contextlib import asynccontextmanager

import pytest

from app.core.cache import build_cache_key, invalidate, invalidate_many, use_cache
import app.core.cache.client as cache_client
from app.core.cache.client import (
    cache_delete_key,
    cache_epoch,
    cache_flush_all,
    cache_get,
    cache_prefix,
    cache_set,
)
from app.settings import settings
from tests.unit.fakes import FakeCacheRedis

IDX = "cache:__idx"


@pytest.fixture
def fake_redis(monkeypatch):
    store = FakeCacheRedis()

    @asynccontextmanager
    async def get_redis():
        yield store

    monkeypatch.setattr(cache_client, "_redis_provider", lambda: get_redis)
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "CACHE_VERSION", "", raising=False)
    monkeypatch.setattr(settings, "CACHE_PREFIX", "cache", raising=False)
    return store


@pytest.mark.unit
@pytest.mark.asyncio
class TestIndexing:
    async def test_set_records_key_in_first_and_second_segment_indexes_without_a_ttl(self, fake_redis):
        await cache_set("cache:characters:7:stats", "x", ttl=30)

        assert fake_redis.sets[f"{IDX}:characters"] == {"cache:characters:7:stats"}
        assert fake_redis.sets[f"{IDX}:characters:7"] == {"cache:characters:7:stats"}
        assert fake_redis.set_calls == [("cache:characters:7:stats", "x", 30)]
        assert fake_redis.expiries == {}

    async def test_two_segment_key_only_in_top_index(self, fake_redis):
        await cache_set("cache:characters:7", "x")

        assert set(fake_redis.sets) == {f"{IDX}:characters"}

    async def test_foreign_keys_are_not_indexed(self, fake_redis):
        await cache_set("fixed:9", "x")

        assert fake_redis.sets == {}
        assert await cache_get("fixed:9") == "x"

    async def test_index_names_follow_the_version_prefix(self, fake_redis, monkeypatch):
        monkeypatch.setattr(settings, "CACHE_VERSION", "r2", raising=False)

        assert cache_prefix() == "cache:r2"
        await cache_set("cache:r2:spells:get_all", "x")

        assert "cache:r2:__idx:spells" in fake_redis.sets


@pytest.mark.unit
@pytest.mark.asyncio
class TestNamespaceInvalidation:
    async def test_purges_namespace_via_index_without_scanning(self, fake_redis):
        await cache_set("cache:spells:get_all:1=1", "a")
        await cache_set("cache:spells:get_by_id:1=5", "b")
        await cache_set("cache:other:get", "c")

        await invalidate("spells")

        assert fake_redis.data == {"cache:other:get": "c"}
        assert fake_redis.scans == 0
        assert f"{IDX}:spells" not in fake_redis.sets
        assert not any(name.endswith(":purging") or ":purging:" in name for name in fake_redis.sets)

    async def test_second_level_namespace_only_touches_that_entity(self, fake_redis):
        await cache_set("cache:characters:1:stats", "a")
        await cache_set("cache:characters:2:stats", "b")
        await cache_set("cache:characters:1", "flat")

        await invalidate("characters:1")

        assert fake_redis.data == {"cache:characters:2:stats": "b", "cache:characters:1": "flat"}
        assert "cache:characters:1:stats" not in fake_redis.sets[f"{IDX}:characters"]
        assert "cache:characters:2:stats" in fake_redis.sets[f"{IDX}:characters"]

    async def test_top_namespace_also_removes_flat_keys(self, fake_redis):
        await cache_set("cache:characters:1", "flat")
        await cache_set("cache:characters:1:stats", "a")

        await invalidate("characters")

        assert fake_redis.data == {}

    async def test_deep_namespace_filters_the_second_level_index(self, fake_redis):
        await cache_set("cache:a:b:c:one", "1")
        await cache_set("cache:a:b:d:two", "2")

        await invalidate("a:b:c")

        assert fake_redis.data == {"cache:a:b:d:two": "2"}

    async def test_unknown_namespace_is_a_noop(self, fake_redis):
        await invalidate("nothing")

        assert fake_redis.unlinked == []

    async def test_invalidate_many_combines_namespaces_and_exact_keys(self, fake_redis):
        await cache_set("cache:a:get", "1")
        await cache_set("cache:b:get", "2")
        await cache_set("cache:c:get", "3")

        await invalidate_many(["a", "b"], ["cache:c:get"])

        assert fake_redis.data == {}
        assert fake_redis.scans == 0
        assert fake_redis.sets.get(f"{IDX}:c", set()) == set()

    async def test_large_namespace_is_unlinked_in_chunks(self, fake_redis, monkeypatch):
        monkeypatch.setattr(cache_client, "_UNLINK_CHUNK", 2)
        for index in range(5):
            await cache_set(f"cache:big:get:{index}", "x")

        await invalidate("big")

        assert fake_redis.data == {}

    async def test_delete_key_removes_value_and_index_entry(self, fake_redis):
        await cache_set("cache:spells:get_by_id:1=5", "a")
        await cache_set("cache:spells:get_by_id:1=6", "b")

        await cache_delete_key("cache:spells:get_by_id:1=5")

        assert fake_redis.data == {"cache:spells:get_by_id:1=6": "b"}
        assert fake_redis.sets[f"{IDX}:spells"] == {"cache:spells:get_by_id:1=6"}

    async def test_index_overflow_flushes_the_namespace(self, fake_redis, monkeypatch):
        monkeypatch.setattr(settings, "CACHE_INDEX_MAX_KEYS", 3, raising=False)

        for index in range(4):
            await cache_set(f"cache:spells:get_all:{index}", "x")

        assert fake_redis.data == {}
        assert f"{IDX}:spells" not in fake_redis.sets

    async def test_flush_all_scans_and_removes_indexes_too(self, fake_redis):
        await cache_set("cache:a:get", "1")
        fake_redis.data["token_blacklist:abc"] = "keep"

        await cache_flush_all()

        assert fake_redis.data == {"token_blacklist:abc": "keep"}
        assert fake_redis.sets == {}
        assert fake_redis.scans == 1


class _ExplodingRedis:
    """Redis double that fails every connection attempt."""

    def __init__(self):
        self.opens = 0

    def provider(self):
        owner = self

        @asynccontextmanager
        async def get_redis():
            owner.opens += 1
            raise ConnectionError("down")
            yield

        return get_redis


@pytest.mark.unit
@pytest.mark.asyncio
class TestCircuitBreaker:
    async def test_opens_after_repeated_failures_and_skips_redis(self, monkeypatch):
        monkeypatch.setattr(settings, "CACHE_ENABLED", True)
        broken = _ExplodingRedis()
        provider = broken.provider()
        monkeypatch.setattr(cache_client, "_redis_provider", lambda: provider)

        for _ in range(6):
            assert await cache_get("cache:x:get") is None

        assert broken.opens == cache_client._BREAKER_THRESHOLD

    async def test_half_open_after_the_window_and_recovers(self, monkeypatch):
        monkeypatch.setattr(settings, "CACHE_ENABLED", True)
        store = FakeCacheRedis()
        store.data["cache:x:get"] = "v"
        broken = _ExplodingRedis()
        failing = broken.provider()

        @asynccontextmanager
        async def healthy():
            yield store

        current = {"provider": failing}
        monkeypatch.setattr(cache_client, "_redis_provider", lambda: current["provider"])
        # Same provider identity across the window: only time moves.
        clock = {"now": 1000.0}
        monkeypatch.setattr(cache_client.time, "monotonic", lambda: clock["now"])

        for _ in range(cache_client._BREAKER_THRESHOLD):
            await cache_get("cache:x:get")
        assert cache_client._breaker.opened_at is not None

        current["provider"] = healthy
        cache_client._breaker._provider = healthy
        clock["now"] += cache_client._BREAKER_OPEN_SECONDS + 1

        assert await cache_get("cache:x:get") == "v"
        assert cache_client._breaker.opened_at is None


@pytest.mark.unit
@pytest.mark.asyncio
class TestKeyBuilding:
    class Service:
        cache_namespaces = ("things",)

        @use_cache()
        def get_by_id(self, item_id: int) -> int:
            return item_id

        @use_cache()
        def search(self, page: int = 1, search: str | None = None) -> list:
            return [page, search]

    async def test_positional_and_keyword_calls_share_a_key(self, fake_redis):
        service = self.Service()

        await service.get_by_id(5)
        await service.get_by_id(item_id=5)

        assert list(fake_redis.data) == ["cache:things:get_by_id:1=5"]

    async def test_build_cache_key_matches_the_stored_key(self, fake_redis):
        service = self.Service()
        await service.get_by_id(9)

        assert build_cache_key(self.Service.get_by_id, service, 9) == "cache:things:get_by_id:1=9"
        assert build_cache_key(self.Service.get_by_id, service, item_id=9) in fake_redis.data

    async def test_long_search_text_is_hashed_to_a_bounded_key(self, fake_redis):
        service = self.Service()

        await service.search(search="x" * 5000)
        await service.search(search="x" * 5000)

        (key,) = fake_redis.data
        assert len(key) < 120
        assert "x" * 100 not in key

    async def test_distinct_long_searches_do_not_collide(self, fake_redis):
        service = self.Service()

        await service.search(search="a" * 200)
        await service.search(search="b" * 200)

        assert len(fake_redis.data) == 2

    async def test_undecodable_cached_payload_is_a_miss(self, fake_redis):
        from pydantic import BaseModel

        class Out(BaseModel):
            id: int

        class Svc:
            cache_namespaces = ("decode",)

            def __init__(self):
                self.calls = 0

            @use_cache()
            def get(self, item_id: int) -> Out:
                self.calls += 1
                return Out(id=item_id)

        svc = Svc()
        key = build_cache_key(Svc.get, svc, 1)
        await cache_set(key, '{"unexpected": true}')

        result = await svc.get(1)

        assert result == Out(id=1)
        assert svc.calls == 1
        assert fake_redis.data[key] == '{"id":1}'


class _Outage:
    """One stable Redis provider whose availability and per-command failures the test controls."""

    def __init__(self):
        self.store = FakeCacheRedis()
        self.down = False
        self.fail_once: set[str] = set()
        self.opens = 0

        outage = self
        real = self.store

        class Proxy:
            def __getattr__(self, name):
                attr = getattr(real, name)
                if name in outage.fail_once:

                    async def failing(*args, **kwargs):
                        outage.fail_once.discard(name)
                        raise ConnectionError(f"{name} failed")

                    return failing
                return attr

            def pipeline(self, transaction=True):
                return real.pipeline(transaction)

        @asynccontextmanager
        async def get_redis():
            outage.opens += 1
            if outage.down:
                raise ConnectionError("down")
            yield Proxy()

        self.provider = get_redis


@pytest.fixture
def outage(monkeypatch):
    controller = _Outage()
    monkeypatch.setattr(cache_client, "_redis_provider", lambda: controller.provider)
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "CACHE_VERSION", "", raising=False)
    monkeypatch.setattr(settings, "CACHE_PREFIX", "cache", raising=False)
    cache_client._pending.clear()
    return controller


@pytest.mark.unit
@pytest.mark.asyncio
class TestInvalidationSurvivesOutages:
    async def test_purge_during_an_outage_is_replayed_before_the_next_read(self, outage):
        await cache_set("cache:spells:get_by_id:1=5", "stale")
        outage.down = True

        await invalidate("spells")
        outage.down = False

        assert await cache_get("cache:spells:get_by_id:1=5") is None
        assert outage.store.data == {}
        assert not cache_client._pending

    async def test_purge_is_attempted_while_the_breaker_is_open(self, outage):
        await cache_set("cache:spells:get_all:1=1", "stale")
        outage.down = True
        for _ in range(cache_client._BREAKER_THRESHOLD):
            await cache_get("cache:spells:get_all:1=1")
        assert cache_client._breaker.opened_at is not None
        opens_before = outage.opens

        await invalidate("spells")

        assert outage.opens == opens_before + 1
        outage.down = False
        cache_client._breaker.success()
        assert await cache_get("cache:spells:get_all:1=1") is None

    async def test_reads_and_writes_never_touch_the_cache_while_the_purge_cannot_run(self, outage):
        await cache_set("cache:spells:get_by_id:1=5", "stale")
        outage.down = True
        await invalidate("spells")

        assert await cache_get("cache:spells:get_by_id:1=5") is None
        await cache_set("cache:spells:get_by_id:1=6", "new")

        assert set(outage.store.data) == {"cache:spells:get_by_id:1=5"}
        assert cache_client._pending.namespaces == {"spells"}

    async def test_exact_key_purge_is_replayed_too(self, outage):
        await cache_set("cache:characters:7", "stale")
        await cache_set("cache:characters:8", "keep")
        outage.down = True

        await cache_delete_key("cache:characters:7")
        outage.down = False

        assert await cache_get("cache:characters:8") == "keep"
        assert "cache:characters:7" not in outage.store.data

    async def test_a_failed_replay_stays_pending_until_it_succeeds(self, outage):
        await cache_set("cache:spells:get_by_id:1=5", "stale")
        outage.down = True
        await invalidate("spells")
        outage.down = False
        outage.fail_once.add("smembers")

        assert await cache_get("cache:spells:get_by_id:1=5") is None
        assert cache_client._pending.namespaces == {"spells"}

        assert await cache_get("cache:spells:get_by_id:1=5") is None
        assert outage.store.data == {}
        assert not cache_client._pending

    async def test_error_in_the_middle_of_a_purge_loses_nothing(self, outage):
        await cache_set("cache:spells:get_by_id:1=5", "stale")
        await cache_set("cache:spells:get_by_id:1=6", "stale")
        outage.fail_once.add("unlink")

        await invalidate("spells")

        assert outage.store.sets[f"{IDX}:spells"] == {"cache:spells:get_by_id:1=5", "cache:spells:get_by_id:1=6"}
        assert await cache_get("cache:spells:get_by_id:1=5") is None
        assert outage.store.data == {}

    async def test_unlink_failure_keeps_the_index_so_the_keys_stay_findable(self, outage):
        await cache_set("cache:spells:get_by_id:1=5", "stale")
        outage.fail_once.add("unlink")

        await invalidate("spells")

        assert "cache:spells:get_by_id:1=5" in outage.store.data
        assert outage.store.sets[f"{IDX}:spells"] == {"cache:spells:get_by_id:1=5"}
        assert not any(":purging:" in name for name in outage.store.sets)

    async def test_flush_all_failure_is_replayed_and_keeps_foreign_keys(self, outage):
        await cache_set("cache:a:get", "1")
        outage.store.data["token_blacklist:abc"] = "keep"
        outage.down = True

        await cache_flush_all()
        outage.down = False
        await cache_get("cache:a:get")

        assert outage.store.data == {"token_blacklist:abc": "keep"}

    async def test_pending_purges_are_bounded(self, monkeypatch, outage):
        monkeypatch.setattr(cache_client, "_PENDING_MAX_KEYS", 3)
        outage.down = True

        for index in range(5):
            await cache_delete_key(f"cache:characters:{index}")

        assert cache_client._pending.flush is True
        assert cache_client._pending.keys == set()

        outage.down = False
        cache_client._breaker.success()
        outage.store.data["cache:characters:9"] = "x"
        await cache_get("cache:characters:9")

        assert "cache:characters:9" not in outage.store.data

    async def test_every_purge_bumps_the_epoch(self, outage):
        before = await cache_epoch()
        await invalidate("nothing")
        await cache_delete_key("cache:a:1")

        assert before == ""
        assert await cache_epoch() == "2"

    async def test_disabled_cache_records_nothing(self, outage, monkeypatch):
        monkeypatch.setattr(settings, "CACHE_ENABLED", False)
        outage.down = True

        await invalidate("spells")

        assert not cache_client._pending


@pytest.mark.unit
@pytest.mark.asyncio
class TestRefillRace:
    async def test_value_computed_before_a_purge_is_not_kept(self, fake_redis):
        epoch = await cache_epoch()

        await invalidate("spells")
        await cache_set("cache:spells:get_by_id:1=5", "stale", epoch=epoch)

        assert fake_redis.data == {}
        assert fake_redis.sets.get(f"{IDX}:spells", set()) == set()

    async def test_value_computed_after_the_last_purge_is_kept(self, fake_redis):
        await invalidate("spells")
        epoch = await cache_epoch()

        await cache_set("cache:spells:get_by_id:1=5", "fresh", epoch=epoch)

        assert fake_redis.data == {"cache:spells:get_by_id:1=5": "fresh"}

    async def test_flush_all_also_voids_inflight_refills(self, fake_redis):
        epoch = await cache_epoch()

        await cache_flush_all()
        await cache_set("cache:a:get", "stale", epoch=epoch)

        assert fake_redis.data == {}

    async def test_decorated_read_racing_a_write_does_not_cache_the_old_value(self, fake_redis):
        class Svc:
            cache_namespaces = ("racey",)

            def __init__(self):
                self.row = "old"
                self.writes = 0

            @use_cache()
            async def get(self, item_id: int) -> str:
                value = self.row
                if self.writes == 0:
                    self.writes += 1
                    self.row = "new"
                    await invalidate("racey")
                return value

        svc = Svc()

        assert await svc.get(1) == "old"
        assert fake_redis.data == {}
        assert await svc.get(1) == "new"
        assert list(fake_redis.data.values()) == ['"new"']

    async def test_no_epoch_means_the_value_is_not_cached(self, outage):
        class Svc:
            cache_namespaces = ("down",)

            @use_cache()
            async def get(self, item_id: int) -> int:
                outage.down = True
                return item_id

        assert await Svc().get(1) == 1
        outage.down = False
        assert outage.store.data == {}


@pytest.mark.unit
@pytest.mark.asyncio
class TestIndexesAreNotEvictable:
    async def test_existing_index_ttl_is_dropped_on_the_next_write(self, fake_redis):
        fake_redis.expiries[f"{IDX}:spells"] = 100

        await cache_set("cache:spells:get_all:1=1", "x")

        assert f"{IDX}:spells" not in fake_redis.expiries

    async def test_data_keys_keep_their_ttl(self, fake_redis):
        await cache_set("cache:spells:get_all:1=1", "x", ttl=77)

        assert fake_redis.set_calls == [("cache:spells:get_all:1=1", "x", 77)]
