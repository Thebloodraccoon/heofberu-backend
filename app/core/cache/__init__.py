"""
Transparent Redis-backed caching: ``@use_cache`` decorator + ``invalidate``.

The cache is *failsafe*: any Redis failure (connection refused, timeout,
bug) degrades to a cache miss / no-op, never raising into business code.
Switch it off globally with ``CACHE_ENABLED=False`` in a settings stage or
per-call with ``@use_cache(skip_if=...)``.
"""

from app.core.cache.decorator import build_cache_key, use_cache
from app.core.cache.invalidation import flush_all, invalidate, invalidate_many

__all__ = ["use_cache", "build_cache_key", "invalidate", "invalidate_many", "flush_all"]
