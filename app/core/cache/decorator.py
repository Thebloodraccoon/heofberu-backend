"""The ``@use_cache`` decorator: transparent per-call Redis caching.

Usage (service methods, sync stack):

    class SpellService(BaseService[...]):
        cache_namespaces = ("spells",)

        @use_cache()
        def get_all(self, page=1, size=100, filters=None, search=None):
            ...

        @use_cache()
        def get_by_id(self, item_id: int) -> SpellResponse:
            ...

        @use_cache(skip_if=lambda self, item_id: item_id <= 0, ttl=60)
        def get(self, item_id: int) -> SpellResponse:
            ...

Behavior
--------
* The cache key is derived from the namespace, function name and a
  canonical rendering of every argument, so calls that differ in any
  argument land on different keys and identical calls hit the same key.
* The namespace comes from (in order): the ``namespace`` argument, the
  decorated service's ``cache_namespaces[0]``, or ``module.qualname``.
* The deserialization schema is read from the function's return
  annotation at decoration time (so ``Page[XGetAllResponse]`` resolves
  against the service module's globals); override it with ``schema=``.
* ``skip_if`` bypasses the cache entirely for the call when it returns
  truthy (e.g. ``skip_if=lambda self, **_: self.some_flag``).
* ``cache_none=False`` skips storing ``None`` results (useful when a
  cache hit must never mask a missing record).
"""

from collections.abc import Callable
import functools
from typing import Any, get_type_hints

from app.core.cache.client import cache_get, cache_set, cache_enabled, cache_prefix
from app.core.cache.serialization import decode, encode


def use_cache(
        *,
        ttl: int | None = None,
        namespace: str | None = None,
        key_builder: Callable[..., str] | None = None,
        skip_if: Callable[..., bool] | None = None,
        schema: type | None = None,
        cache_none: bool = True,
) -> Callable:
    """Decorate a sync function so its result is cached in Redis."""

    def decorator(func: Callable) -> Callable:
        return_schema = schema if schema is not None else _resolve_return_schema(func)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not cache_enabled():
                return func(*args, **kwargs)

            if skip_if is not None and skip_if(*args, **kwargs):
                return func(*args, **kwargs)

            key = _build_key(namespace, func, args, kwargs, key_builder)
            raw = cache_get(key)
            if raw is not None:
                return decode(raw, return_schema)

            result = func(*args, **kwargs)
            if result is None and not cache_none:
                return result

            cache_set(key, encode(result), ttl)
            return result

        return wrapper

    return decorator


def _resolve_return_schema(func: Callable) -> Any:
    """Resolve the return annotation against the decorated function's globals."""

    try:
        hints = get_type_hints(func)
    except Exception:
        return None
    return hints.get("return")


def _build_key(
        namespace: str | None,
        func: Callable,
        args: tuple,
        kwargs: dict,
        key_builder: Callable[..., str] | None,
) -> str:
    if key_builder is not None:
        return key_builder(*args, **kwargs)

    parts = [_resolve_namespace(namespace, args, func), func.__name__]
    for index, value in enumerate(args[1:], start=1):
        parts.append(f"{index}={_canonical(value)}")

    for name in sorted(kwargs):
        parts.append(f"{name}={_canonical(kwargs[name])}")

    return f"{cache_prefix()}:{':'.join(parts)}"


def _resolve_namespace(explicit: str | None, args: tuple, func: Callable) -> str:
    if explicit is not None:
        return explicit

    if args:
        namespaces = getattr(args[0], "cache_namespaces", ())
        if namespaces:
            return namespaces[0]

    return f"{func.__module__}.{func.__qualname__}"


def _canonical(value: Any) -> str:
    """Stable string rendering of an argument for cache keys.

    Dicts are key-sorted so ``filters={"name": x, "kind": y}`` and
    ``filters={"kind": y, "name": x}`` produce the same key. ``None``
    values are dropped so defaulted kwargs never fragment the cache.
    """

    if isinstance(value, dict):
        return "{" + ",".join(
            f"{k}={_canonical(v)}" for k, v in sorted(value.items()) if v is not None
        ) + "}"

    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_canonical(v) for v in value) + "]"

    return str(value)
