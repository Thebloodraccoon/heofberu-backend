"""Subclass cache coordination: one invalidation point shared by the subdomain's capabilities."""

from app.core.cache import invalidate

# ``subclass_features`` is the subclass's own feature-list cache;
# ``features`` is the central by-id feature cache (``GET /features/{id}``
# can now serve source-owned features).
SUBCLASS_CACHE_NAMESPACES = ("classes", "subclass_features", "features")


async def invalidate_subclass_cache() -> None:
    """
    Purge every cache namespace a subclass read can hit.

    ``GET /classes/{id}`` (``classes``, which also embeds every subclass
    with its own SUBCLASS-source features), the subclass's own feature
    listing (``subclass_features``) and the central feature by-id cache
    (``features``) are all served from cache. Any write to a subclass —
    base fields or its own features — must call this after its
    transaction commits, so the subdomain's capability services
    (crud/features) share a single invalidation point instead of each
    re-declaring the namespace tuple.
    """

    for namespace in SUBCLASS_CACHE_NAMESPACES:
        await invalidate(namespace)
