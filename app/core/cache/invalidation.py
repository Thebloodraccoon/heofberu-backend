"""Cache invalidation: purge an entire namespace.

Services that write to a catalog call ``invalidate(namespace)`` after the
write (via ``BaseService._invalidate_cache``), which deletes every key
under ``<prefix>:<namespace>:*``. Cross-namespace invalidation is declared
per service: e.g. ``ClassService.cache_namespaces = ("classes", "features")``
because creating a class also writes features table rows that the
``GET /features`` listing is filtered by.
"""

from app.core.cache.client import cache_delete_prefix


async def invalidate(namespace: str) -> None:
    """Delete all cached entries under the given namespace (best-effort)."""

    await cache_delete_prefix(namespace)
