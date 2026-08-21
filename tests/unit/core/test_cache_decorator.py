"""
Unit tests for the ``@use_cache`` decorator against a fake Redis store.

The cache layer is exercised with an in-memory ``FakeRedis`` that mimics the
async ``get``/``set``/``scan_iter``/``delete`` surface, injected by patching
``app.crud.cache.client._redis_provider``. ``CACHE_ENABLED`` is flipped on
per-test (``app.settings.test`` keeps it off by default).
"""

from contextlib import asynccontextmanager
import fnmatch
from types import SimpleNamespace

from pydantic import BaseModel, ConfigDict
import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

from app.core.base.cached_service import CachedService
from app.core.base.service import Page
from app.core.cache import invalidate, use_cache
import app.core.cache.client as cache_client
from app.settings import settings


class FakeRedis:
    """Minimal in-memory stand-in for the async Redis surface the cache uses."""

    def __init__(self):
        self.data = {}
        self.sets = []

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, ex=None):
        self.sets.append((key, value, ex))
        self.data[key] = value
        return True

    async def scan_iter(self, match=None, count=100):
        keys = list(self.data)
        if match is not None:
            keys = [key for key in keys if fnmatch.fnmatchcase(key, match)]
        for key in keys:
            yield key

    async def delete(self, *keys):
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


class Greeter:
    cache_namespaces = ("greetings",)

    def __init__(self):
        self.calls = 0

    @use_cache()
    def greet(self, name: str = "world") -> str:
        self.calls += 1
        return f"hi {name}"


class FilterService:
    cache_namespaces = ("things",)

    def __init__(self):
        self.calls = 0

    @use_cache()
    def search(self, filters: dict | None = None) -> list:
        self.calls += 1
        return ["found"]


class Maybe:
    cache_namespaces = ("maybe",)

    def __init__(self):
        self.calls = 0

    @use_cache()
    def get(self) -> str | None:
        self.calls += 1
        return None


class Skippy:
    cache_namespaces = ("skippy",)

    def __init__(self):
        self.calls = 0

    @use_cache(skip_if=lambda self, **_: True)
    def get(self, value: int = 1) -> int:
        self.calls += 1
        return value


class TtlService:
    cache_namespaces = ("ttl",)

    def __init__(self):
        self.calls = 0

    @use_cache(ttl=60)
    def get(self) -> int:
        self.calls += 1
        return 7


class Person(BaseModel):
    id: int
    name: str


class People:
    cache_namespaces = ("people",)

    def __init__(self):
        self.calls = 0

    @use_cache()
    def get(self, person_id: int) -> Person:
        self.calls += 1
        return Person(id=person_id, name="Ada")


class Other:
    cache_namespaces = ("other",)

    def __init__(self):
        self.calls = 0

    @use_cache()
    def get(self) -> int:
        self.calls += 1
        return 7


@use_cache()
def standalone_lookup(value: int = 1) -> int:
    return value * 2


@pytest.mark.unit
@pytest.mark.asyncio
class TestUseCache:
    async def test_second_call_hits_cache(self, fake_redis):
        greeter = Greeter()

        assert await greeter.greet("Alice") == "hi Alice"
        assert await greeter.greet("Alice") == "hi Alice"

        assert greeter.calls == 1
        assert len(fake_redis.data) == 1

    async def test_distinct_args_land_on_distinct_keys(self, fake_redis):
        greeter = Greeter()

        await greeter.greet("A")
        await greeter.greet("B")

        assert greeter.calls == 2
        assert len(fake_redis.data) == 2

    async def test_dict_keyword_order_does_not_fragment_cache(self, fake_redis):
        service = FilterService()

        await service.search(filters={"a": 1, "b": 2})
        await service.search(filters={"b": 2, "a": 1})

        assert service.calls == 1
        assert len(fake_redis.data) == 1

    async def test_none_result_is_cached_by_default(self, fake_redis):
        maybe = Maybe()

        await maybe.get()
        await maybe.get()

        assert maybe.calls == 1

    async def test_cache_none_false_never_stores(self, fake_redis):
        class NoNoneCache:
            cache_namespaces = ("maybe",)

            def __init__(self):
                self.calls = 0

            @use_cache(cache_none=False)
            def get(self) -> str | None:
                self.calls += 1
                return None

        instance = NoNoneCache()
        await instance.get()
        await instance.get()

        assert instance.calls == 2
        assert fake_redis.data == {}

    async def test_skip_if_bypasses_cache(self, fake_redis):
        skippy = Skippy()

        await skippy.get()
        await skippy.get()

        assert skippy.calls == 2
        assert fake_redis.data == {}

    async def test_disabled_cache_passes_through(self, fake_redis, monkeypatch):
        monkeypatch.setattr(settings, "CACHE_ENABLED", False)
        greeter = Greeter()

        await greeter.greet("Alice")
        await greeter.greet("Alice")

        assert greeter.calls == 2
        assert fake_redis.data == {}

    async def test_custom_ttl_is_passed_to_set(self, fake_redis):
        service = TtlService()

        await service.get()

        assert fake_redis.sets[0][2] == 60

    async def test_default_ttl_comes_from_settings(self, fake_redis, monkeypatch):
        monkeypatch.setattr(settings, "CACHE_TTL_DEFAULT", 123)
        greeter = Greeter()

        await greeter.greet("Alice")

        assert fake_redis.sets[0][2] == 123

    async def test_result_decoded_back_into_return_schema(self, fake_redis):
        people = People()

        first = await people.get(1)
        second = await people.get(1)

        assert isinstance(second, Person)
        assert first == second
        assert people.calls == 1

    async def test_namespace_comes_from_cache_namespaces(self, fake_redis):
        greeter = Greeter()

        await greeter.greet("Alice")

        assert any(key.startswith("cache:greetings:") for key in fake_redis.data)

    async def test_namespace_falls_back_to_module_qualname(self, fake_redis):
        assert await standalone_lookup(value=5) == 10
        assert await standalone_lookup(value=5) == 10

        assert any(".standalone_lookup" in key for key in fake_redis.data)

    async def test_custom_key_builder_replaces_key_entirely(self, fake_redis, monkeypatch):
        class Custom:
            cache_namespaces = ("custom",)

            def __init__(self):
                self.calls = 0

            @use_cache(key_builder=lambda self, value: f"fixed:{value}")
            def get(self, value: int = 1) -> int:
                self.calls += 1
                return value

        custom = Custom()
        await custom.get(value=9)
        await custom.get(value=9)

        assert custom.calls == 1
        assert list(fake_redis.data) == ["fixed:9"]


@pytest.mark.unit
@pytest.mark.asyncio
class TestInvalidation:
    async def test_invalidate_purges_only_the_target_namespace(self, fake_redis):
        greeter = Greeter()
        await greeter.greet("Alice")
        await greeter.greet("Bob")
        other = Other()
        await other.get()

        await invalidate("greetings")

        assert fake_redis.data == {"cache:other:get": "7"}

        await other.get()
        assert other.calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestFailsafe:
    async def test_redis_down_degrades_to_miss(self, fake_redis, monkeypatch):
        @asynccontextmanager
        async def broken_redis():
            raise ConnectionError("down")
            yield

        monkeypatch.setattr(cache_client, "_redis_provider", lambda: broken_redis)
        greeter = Greeter()

        assert await greeter.greet("Alice") == "hi Alice"
        assert await greeter.greet("Alice") == "hi Alice"

        assert greeter.calls == 2

    async def test_redis_down_does_not_break_invalidation(self, fake_redis, monkeypatch):
        @asynccontextmanager
        async def broken_redis():
            raise ConnectionError("down")
            yield

        monkeypatch.setattr(cache_client, "_redis_provider", lambda: broken_redis)

        await invalidate("greetings")


@pytest.mark.unit
@pytest.mark.asyncio
class TestNamespaceResolution:
    async def test_namespace_prefers_first_cache_namespace_entry(self, fake_redis):
        class MultiNamespace:
            cache_namespaces = ("first", "second")

            def __init__(self):
                self.calls = 0

            @use_cache()
            def get(self) -> int:
                self.calls += 1
                return 1

        multi = MultiNamespace()
        await multi.get()

        assert any(key.startswith("cache:first:") for key in fake_redis.data)


_DynBase = declarative_base()


class DynItemModel(_DynBase):
    __tablename__ = "dyn_catalog_items"
    id = Column(Integer, primary_key=True)
    name = Column(String)


class DynItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class DynItemIn(BaseModel):
    name: str


class DynRepo:
    """Recording fake standing in for ``BaseRepository`` on the read paths."""

    def __init__(self, row):
        self.row = row
        self.model = DynItemModel
        self.get_by_id_calls = 0
        self.get_brief_calls = 0
        self.count_calls = 0

    async def get_by_id(self, item_id):
        self.get_by_id_calls += 1
        return self.row

    async def get_brief(self, *columns, order_by=None, skip=0, limit=100, filters=None, search=None):
        self.get_brief_calls += 1
        return [self.row]

    async def count(self, *, filters=None, search=None):
        self.count_calls += 1
        return 1


class DynCatalog(CachedService[DynItemModel, DynItemIn, DynItemIn, DynItemOut, DynItemOut]):
    cache_namespaces = ("dyn_catalog",)

    def __init__(self, repo):
        super().__init__(repository=repo, response_schema=DynItemOut, get_all_schema=DynItemOut)


@pytest.mark.unit
@pytest.mark.asyncio
class TestCachedServiceDynamicSchema:
    """``CachedService``'s TypeVar-annotated reads resolve the schema per-call."""

    async def test_get_by_id_decodes_into_response_schema(self, fake_redis):
        repo = DynRepo(SimpleNamespace(id=7, name="Elf"))
        service = DynCatalog(repo)

        first = await service.get_by_id(7)
        second = await service.get_by_id(7)

        assert isinstance(first, DynItemOut)
        assert first == second
        assert repo.get_by_id_calls == 1
        assert any(key.startswith("cache:dyn_catalog:get_by_id:") for key in fake_redis.data)

    async def test_get_all_decodes_into_page_of_get_all_schema(self, fake_redis):
        repo = DynRepo(SimpleNamespace(id=1, name="Human"))
        service = DynCatalog(repo)

        first = await service.get_all(page=1, size=10)
        second = await service.get_all(page=1, size=10)

        assert isinstance(first, Page)
        assert isinstance(first.items[0], DynItemOut)
        assert first.total == 1
        assert first == second
        assert repo.count_calls == 1
        assert repo.get_brief_calls == 1

    async def test_missing_return_annotation_uses_instance_response_schema(self, fake_redis):
        class NoHintService:
            cache_namespaces = ("no_hint",)
            response_schema = DynItemOut

            def __init__(self):
                self.calls = 0

            @use_cache()
            def get(self, item_id: int):
                self.calls += 1
                return DynItemOut(id=item_id, name="X")

        service = NoHintService()

        first = await service.get(item_id=3)
        second = await service.get(item_id=3)

        assert isinstance(first, DynItemOut)
        assert first == second
        assert service.calls == 1
