"""Background cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

# ``background_features`` is the background's own feature-list cache;
# ``features`` is the central by-id feature cache (``GET /features/{id}``
# can now serve source-owned features).
BACKGROUND_CACHE_NAMESPACES = ("backgrounds", "background_features", "features", "nested_items")


async def invalidate_background_cache() -> None:
    """
    Purge every cache namespace a background read can hit.

    ``GET /backgrounds/{id}`` (``backgrounds``), the background's own
    feature listing (``background_features``), the central feature by-id
    cache (``features``) and the per-source item listing
    (``nested_items``) are all served from cache. Any write to a
    background — base fields, granted skills, starting items, or its own
    features — must call this after its transaction commits, so the four
    capability services (crud/features/skills/items) share a single
    invalidation point instead of each re-declaring the namespace tuple.
    """

    for namespace in BACKGROUND_CACHE_NAMESPACES:
        await invalidate(namespace)
