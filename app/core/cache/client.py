"""Low-level Redis cache store.

All access goes through ``settings.get_redis()`` (the same async context
manager used by the JWT blacklist) so no connection lifecycle is managed
here. Every operation is wrapped in try/except: if Redis is down the cache
behaves as an always-miss cache and the request proceeds to the database.
"""

import logging
from typing import Any, Callable

from app.settings import settings

logger = logging.getLogger(__name__)


def _redis_provider() -> Callable:
    """Return ``settings.get_redis`` so tests can monkeypatch the provider."""

    return settings.get_redis


def cache_enabled() -> bool:
    """Whether caching is globally enabled (``CACHE_ENABLED`` stage setting)."""

    try:
        return bool(getattr(settings, "CACHE_ENABLED", True))
    except Exception:
        return True


def cache_prefix() -> str:
    """Key prefix for all cached entries (``CACHE_PREFIX`` stage setting)."""
    return getattr(settings, "CACHE_PREFIX", "cache")


def cache_ttl_default() -> int:
    """Default TTL in seconds (``CACHE_TTL_DEFAULT`` stage setting)."""

    return getattr(settings, "CACHE_TTL_DEFAULT", 86400)


async def cache_get(key: str) -> Any:
    """Fetch a raw cached value; returns ``None`` on miss or Redis failure."""

    if not cache_enabled():
        return None
    try:
        async with _redis_provider()() as redis:
            return await redis.get(key)

    except Exception:
        logger.warning("Cache GET failed for %s", key, exc_info=True)
        return None


async def cache_set(key: str, value: Any, ttl: int | None = None) -> None:
    """Store a raw value with an optional TTL; no-op when caching is disabled."""

    if not cache_enabled():
        return

    if ttl is None:
        ttl = cache_ttl_default()

    try:
        async with _redis_provider()() as redis:
            await redis.set(key, value, ex=ttl)
    except Exception:
        logger.warning("Cache SET failed for %s", key, exc_info=True)


async def cache_delete_prefix(namespace: str) -> None:
    """Delete every key under ``<prefix>:<namespace>:*`` (best-effort)."""

    if not cache_enabled():
        return

    pattern = f"{cache_prefix()}:{namespace}:*"
    try:
        async with _redis_provider()() as redis:
            keys = [key async for key in redis.scan_iter(match=pattern, count=500)]
            if keys:
                await redis.delete(*keys)

    except Exception:
        logger.warning("Cache invalidation failed for %s", namespace, exc_info=True)
