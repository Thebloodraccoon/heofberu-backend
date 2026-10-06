"""
Cache invalidation: purge an entire namespace.

Services that write to a catalog call ``invalidate(namespace)`` after the
write (via ``BaseService._invalidate_cache``), which deletes every key
under ``<prefix>:<namespace>:*`` using the per-namespace key indexes (no
keyspace scan; see ``app.core.cache.client``). Inside a transaction, schedule
the purge with ``app.core.base.transaction.invalidate_after_commit`` so it
runs only after ``COMMIT``. Cross-namespace invalidation is declared
per service: e.g. ``ClassService.cache_namespaces = ("classes", "features")``
because creating a class also writes features table rows that the
``GET /features`` listing is filtered by.
"""

from app.core.cache.client import cache_delete_many, cache_delete_prefix, cache_flush_all


async def invalidate(namespace: str) -> None:
    """Delete all cached entries under the given namespace (best-effort)."""

    await cache_delete_prefix(namespace)


async def invalidate_many(namespaces: list[str], keys: list[str] | None = None) -> None:
    """
    Delete all cached entries under many namespaces, plus any extra exact
    ``keys``, in one Redis connection instead of one per namespace/key —
    use this instead of looping ``invalidate()`` when a single write
    affects many entities (e.g. every character granted a feature a GM
    just edited).
    """

    await cache_delete_many(namespaces, keys)


async def flush_all() -> None:
    """
    Delete every cached entry across all namespaces (best-effort).

    Only keys under the app's ``CACHE_PREFIX`` are removed — unrelated
    Redis keys (e.g. the JWT blacklist) are preserved.
    """

    await cache_flush_all()
