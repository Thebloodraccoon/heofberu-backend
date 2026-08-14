"""
The ``@use_cache`` decorator: transparent per-call Redis caching.

Usage (service methods, async stack):

    class SpellService(BaseService[...]):
        cache_namespaces = ("spells",)

        @use_cache()
        async def get_all(self, page=1, size=100, filters=None, search=None):
            ...

        @use_cache()
        async def get_by_id(self, item_id: int) -> SpellResponse:
            ...

        @use_cache(skip_if=lambda self, item_id: item_id <= 0, ttl=60)
        async def get(self, item_id: int) -> SpellResponse:
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
  When the annotation is missing or still carries an unbound
  ``TypeVar`` (generic cached base methods such as
  ``CachedService.get_all``), the schema is instead resolved per-call
  from the concrete instance's ``get_all_schema``/``response_schema``.
* ``skip_if`` bypasses the cache entirely for the call when it returns
  truthy (e.g. ``skip_if=lambda self, **_: self.some_flag``).
* ``cache_none=False`` skips storing ``None`` results (useful when a
  cache hit must never mask a missing record).

The generated wrapper is always a coroutine function; a decorated
*sync* function is called directly inside it and its plain result is
returned. Every cached/uncached branch is awaited by the caller.
"""

from collections.abc import Callable
import functools
import inspect
from typing import Any, get_type_hints

from app.core.cache.client import cache_enabled, cache_get, cache_prefix, cache_set
from app.core.cache.serialization import decode, encode

_DYNAMIC_SCHEMA = object()  # sentinel: resolve the schema per-call from the service instance


def use_cache(
    *,
    ttl: int | None = None,
    namespace: str | None = None,
    key_builder: Callable[..., str] | None = None,
    skip_if: Callable[..., bool] | None = None,
    schema: type | None = None,
    cache_none: bool = True,
) -> Callable:
    """Decorate a sync or async function so its result is cached in Redis."""

    def decorator(func: Callable) -> Callable:
        return_schema = schema if schema is not None else _resolve_return_schema(func)
        is_coroutine = inspect.iscoroutinefunction(func)

        async def _call(*args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)
            return await result if is_coroutine else result

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not cache_enabled():
                return await _call(*args, **kwargs)

            if skip_if is not None and skip_if(*args, **kwargs):
                return await _call(*args, **kwargs)

            call_schema = return_schema
            if call_schema is _DYNAMIC_SCHEMA:
                call_schema = _resolve_call_schema(func, args)

            key = _build_key(namespace, func, args, kwargs, key_builder)
            raw = await cache_get(key)
            if raw is not None:
                return decode(raw, call_schema)

            result = await _call(*args, **kwargs)
            if result is None and not cache_none:
                return result

            await cache_set(key, encode(result), ttl)
            return result

        return wrapper

    return decorator


def _resolve_return_schema(func: Callable) -> Any:
    """Resolve the return annotation against the decorated function's globals."""

    try:
        hints = get_type_hints(func)
    except Exception:
        return None

    hint = hints.get("return")
    if hint is None or _contains_unbound_typevar(hint):
        return _DYNAMIC_SCHEMA

    return hint


def _contains_unbound_typevar(hint: Any) -> bool:
    """
    Return whether ``hint`` references an unbound ``TypeVar`` (i.e. isn't concrete).

    Covers bare ``TypeVar`` returns and subscripted generics. Pydantic v2
    generic aliases (``Page[~GetAllSchema]``) do *not* expose their bare
    type parameter through ``__args__``/``__parameters__`` — they stash it
    in ``__pydantic_generic_metadata__["parameters"]`` (empty for a
    concrete parametrization like ``Page[RaceGetAllResponse]``). A
    ``TypeVar`` instance is recognized by class name because
    ``typing_extensions.TypeVar`` does not subclass ``typing.TypeVar``.
    """

    if hint.__class__.__name__ == "TypeVar":
        return True

    metadata = getattr(hint, "__pydantic_generic_metadata__", None)
    if metadata and metadata.get("parameters"):
        return True

    params = getattr(hint, "__parameters__", None)
    if params:
        return any(_contains_unbound_typevar(param) for param in params)

    args = getattr(hint, "__args__", None)
    if args:
        return any(_contains_unbound_typevar(arg) for arg in args)

    return False


def _resolve_call_schema(func: Callable, args: tuple) -> Any:
    """
    Resolve the deserialization schema from the concrete service instance.

    Used by generic cached base methods whose annotation only carries a
    ``TypeVar``:

    * ``CachedService.get_all``/``get_by_id`` — the concrete schema is
      read off the instance at call time (``get_all_schema`` for listings
      wrapped in ``Page``, ``response_schema`` for detail reads).
    * ``NestedCollectionService.list_for_source`` — same idea, but the
      per-call schema must be wrapped in ``list[...]`` instead of
      ``Page[...]``, since the method returns a bare list, not a page.
      Distinguished from ``get_all`` by name so a plain single-object
      ``response_schema`` isn't handed to ``decode`` for a list payload
      (which would fail: ``Model.model_validate_json`` rejects a
      JSON array).
    """

    if not args:
        return None

    instance = args[0]
    if func.__name__ == "get_all":
        item_schema = getattr(instance, "get_all_schema", None)
        if item_schema is not None:
            from app.core.base.service import Page  # deferred to avoid an import cycle

            return Page[item_schema]

    if func.__name__ == "list_for_source":
        item_schema = getattr(instance, "response_schema", None)
        if item_schema is not None:
            return list[item_schema]

    return getattr(instance, "response_schema", None)


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
    """
    Stable string rendering of an argument for cache keys.

    Dicts are key-sorted so ``filters={"name": x, "kind": y}`` and
    ``filters={"kind": y, "name": x}`` produce the same key. ``None``
    values are dropped so defaulted kwargs never fragment the cache.
    """

    if isinstance(value, dict):
        return "{" + ",".join(f"{k}={_canonical(v)}" for k, v in sorted(value.items()) if v is not None) + "}"

    if isinstance(value, list | tuple):
        return "[" + ",".join(_canonical(v) for v in value) + "]"

    return str(value)
