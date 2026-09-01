"""Feature cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

FEATURE_CACHE_NAMESPACES = ("features",)

async def invalidate_feature_cache() -> None:
    """
    Purge every cache namespace a central feature read can hit.

    ``GET /features`` (the ``features`` namespace) is served from cache.
    The per-catalog feature-list namespaces (``race_features`` etc.) are
    purged by ``FeatureCrudService._purge_feature_cache`` via
    ``SOURCE_FEATURE_LIST_NAMESPACE``.
    """

    for namespace in FEATURE_CACHE_NAMESPACES:
        await invalidate(namespace)
