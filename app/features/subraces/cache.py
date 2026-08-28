"""Subrace cache coordination: one invalidation point shared by the subdomain's capabilities."""

from app.core.cache import invalidate

# ``subrace_features`` is the subrace's own feature-list cache;
# ``features`` is the central by-id feature cache (``GET /features/{id}``
# can now serve source-owned features).
SUBRACE_CACHE_NAMESPACES = ("races", "subrace_features", "features")


async def invalidate_subrace_cache() -> None:
    """
    Purge every cache namespace a subrace read can hit.

    ``GET /races`` and ``GET /races/{id}`` (``races``, which also embeds
    every subrace), the subrace's own feature listing
    (``subrace_features``) and the central feature by-id cache
    (``features``) are all served from cache. Any write to a subrace —
    base fields, ability bonuses, or its own features — must call this
    after its transaction commits, so the subdomain's capability services
    (crud/features/ability_bonuses) share a single invalidation point
    instead of each re-declaring the namespace tuple.
    """

    for namespace in SUBRACE_CACHE_NAMESPACES:
        await invalidate(namespace)
