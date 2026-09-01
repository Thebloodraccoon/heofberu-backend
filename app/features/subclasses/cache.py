"""Subclass cache coordination: one invalidation point shared by the subdomain's capabilities."""

from app.core.cache import invalidate

# ``subclass_features`` is the subclass's own feature-list cache;
# ``features`` is the central by-id feature cache.
SUBCLASS_CACHE_NAMESPACES = ("classes", "subclass_features", "features")


async def invalidate_subclass_cache() -> None:
    """Purge every cache namespace a subclass read can hit."""

    for namespace in SUBCLASS_CACHE_NAMESPACES:
        await invalidate(namespace)
