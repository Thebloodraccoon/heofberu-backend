"""Feature cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

FEATURE_CACHE_NAMESPACES = ("features",)


async def invalidate_feature_cache() -> None:
    """
    Purge every cache namespace a feature read can hit.

    ``GET /features`` (``features`` namespace) is served from cache. Any
    write to a feature — standalone CRUD via ``/features`` or source-owned
    features through a parent record — must call this after its
    transaction commits. The parent catalogs (race/subrace/class/
    background/feat) already include ``"features"`` in their
    ``cache_namespaces`` for the same reason.
    """
    for namespace in FEATURE_CACHE_NAMESPACES:
        await invalidate(namespace)
