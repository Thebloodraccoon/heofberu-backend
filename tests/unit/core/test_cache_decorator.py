"""Unit tests for the ``@use_cache`` decorator against a fake Redis store.

The cache layer is exercised with an in-memory ``FakeRedis`` that mimics the
``get``/``set``/``scan_iter``/``delete`` surface, injected by patching
``app.core.cache.client._redis_provider``. ``CACHE_ENABLED`` is flipped on
per-test (``app.settings.test`` keeps it off by default).
"""

from contextlib import contextmanager
import fnmatch
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

import app.core.cache.client as cache_client
from app.core.cache import invalidate, use_cache
from app.settings import settings


class FakeRedis:
    """Minimal in-memory stand-in for the Redis client surface the cache uses."""

    def __init__(self):
        self.data = {}
        self.sets = []

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ex=None):
        self.sets.append((key, value, ex))
        self.data[key] = value
        return True

    def scan_iter(self, match=None, count=100):
        keys = list(self.data)
        if match is None:
            return iter(keys)
        return iter(key for key in keys if fnmatch.fnmatchcase(key, match))

    def delete(self, *keys):
        removed = 0
        for key in keys:
            if self.data.pop(key, None) is not None:
                removed += 1
        return removed


@pytest.fixture
def fake_redis(monkeypatch):
    """Patch the Redis provider with a fresh ``FakeRedis`` and enable caching."""
    store = FakeRedis()

    @contextmanager
    def get_redis():
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
class TestUseCache:
    def test_second_call_hits_cache(self, fake_redis):
        greeter = Greeter()

        assert greeter.greet("Alice") == "hi Alice"
        assert greeter.greet("Alice") == "hi Alice"

        assert greeter.calls == 1
        assert len(fake_redis.data) == 1

    def test_distinct_args_land_on_distinct_keys(self, fake_redis):
        greeter = Greeter()

        greeter.greet("A")
        greeter.greet("B")

        assert greeter.calls == 2
        assert len(fake_redis.data) == 2

    def test_dict_keyword_order_does_not_fragment_cache(self, fake_redis):
        service = FilterService()

        service.search(filters={"a": 1, "b": 2})
        service.search(filters={"b": 2, "a": 1})

        assert service.calls == 1
        assert len(fake_redis.data) == 1

    def test_none_result_is_cached_by_default(self, fake_redis):
        maybe = Maybe()

        maybe.get()
        maybe.get()

        assert maybe.calls == 1

    def test_cache_none_false_never_stores(self, fake_redis):
        class NoNoneCache:
            cache_namespaces = ("maybe",)

            def __init__(self):
                self.calls = 0

            @use_cache(cache_none=False)
            def get(self) -> str | None:
                self.calls += 1
                return None

        instance = NoNoneCache()
        instance.get()
        instance.get()

        assert instance.calls == 2
        assert fake_redis.data == {}

    def test_skip_if_bypasses_cache(self, fake_redis):
        skippy = Skippy()

        skippy.get()
        skippy.get()

        assert skippy.calls == 2
        assert fake_redis.data == {}

    def test_disabled_cache_passes_through(self, fake_redis, monkeypatch):
        monkeypatch.setattr(settings, "CACHE_ENABLED", False)
        greeter = Greeter()

        greeter.greet("Alice")
        greeter.greet("Alice")

        assert greeter.calls == 2
        assert fake_redis.data == {}

    def test_custom_ttl_is_passed_to_set(self, fake_redis):
        service = TtlService()

        service.get()

        assert fake_redis.sets[0][2] == 60

    def test_default_ttl_comes_from_settings(self, fake_redis, monkeypatch):
        monkeypatch.setattr(settings, "CACHE_TTL_DEFAULT", 123)
        greeter = Greeter()

        greeter.greet("Alice")

        assert fake_redis.sets[0][2] == 123

    def test_result_decoded_back_into_return_schema(self, fake_redis):
        people = People()

        first = people.get(1)
        second = people.get(1)

        assert isinstance(second, Person)
        assert first == second
        assert people.calls == 1

    def test_namespace_comes_from_cache_namespaces(self, fake_redis):
        greeter = Greeter()

        greeter.greet("Alice")

        assert any(key.startswith("cache:greetings:") for key in fake_redis.data)

    def test_namespace_falls_back_to_module_qualname(self, fake_redis):
        assert standalone_lookup(value=5) == 10
        assert standalone_lookup(value=5) == 10

        assert any(".standalone_lookup" in key for key in fake_redis.data)

    def test_custom_key_builder_replaces_key_entirely(self, fake_redis, monkeypatch):
        class Custom:
            cache_namespaces = ("custom",)

            def __init__(self):
                self.calls = 0

            @use_cache(key_builder=lambda self, value: f"fixed:{value}")
            def get(self, value: int = 1) -> int:
                self.calls += 1
                return value

        custom = Custom()
        custom.get(value=9)
        custom.get(value=9)

        assert custom.calls == 1
        assert list(fake_redis.data) == ["fixed:9"]


@pytest.mark.unit
class TestInvalidation:
    def test_invalidate_purges_only_the_target_namespace(self, fake_redis):
        greeter = Greeter()
        greeter.greet("Alice")
        greeter.greet("Bob")
        other = Other()
        other.get()

        invalidate("greetings")

        assert fake_redis.data == {}

        other.get()
        assert other.calls == 1


@pytest.mark.unit
class TestFailsafe:
    def test_redis_down_degrades_to_miss(self, fake_redis, monkeypatch):
        @contextmanager
        def broken_redis():
            raise ConnectionError("down")

        monkeypatch.setattr(cache_client, "_redis_provider", lambda: broken_redis)
        greeter = Greeter()

        assert greeter.greet("Alice") == "hi Alice"
        assert greeter.greet("Alice") == "hi Alice"

        assert greeter.calls == 2

    def test_redis_down_does_not_break_invalidation(self, fake_redis, monkeypatch):
        @contextmanager
        def broken_redis():
            raise ConnectionError("down")

        monkeypatch.setattr(cache_client, "_redis_provider", lambda: broken_redis)

        invalidate("greetings")


@pytest.mark.unit
class TestNamespaceResolution:
    def test_namespace_prefers_first_cache_namespace_entry(self, fake_redis):
        class MultiNamespace:
            cache_namespaces = ("first", "second")

            def __init__(self):
                self.calls = 0

            @use_cache()
            def get(self) -> int:
                self.calls += 1
                return 1

        multi = MultiNamespace()
        multi.get()

        assert any(key.startswith("cache:first:") for key in fake_redis.data)
