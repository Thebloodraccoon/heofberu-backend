"""Background cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

BACKGROUND_CACHE_NAMESPACES = ("backgrounds", "nested_features", "nested_items")


async def invalidate_background_cache() -> None:
    """
    Purge every cache namespace a background read can hit.

    ``GET /backgrounds/{id}`` (``backgrounds``), the per-source feature
    listing (``nested_features``) and the per-source item listing
    (``nested_items``) are all served from cache. Any write to a
    background — base fields, granted skills, starting items, or its own
    features — must call this after its transaction commits, so the four
    capability services (crud/features/skills/items) share a single
    invalidation point instead of each re-declaring the namespace tuple.
    """

    for namespace in BACKGROUND_CACHE_NAMESPACES:
        await invalidate(namespace)
