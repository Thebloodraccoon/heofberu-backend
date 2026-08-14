"""Feat cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

FEAT_CACHE_NAMESPACES = ("feats", "nested_features")


async def invalidate_feat_cache() -> None:
    """
    Purge every cache namespace a feat read can hit.

    ``GET /feats/{id}`` (``feats``) and the per-source feature listing
    (``nested_features``) are both served from cache. Any write to a feat —
    base fields, ASI choices, or its own features — must call this after its
    transaction commits, so the capability services (crud/features/asi)
    share a single invalidation point instead of each re-declaring the
    namespace tuple.
    """
    for namespace in FEAT_CACHE_NAMESPACES:
        await invalidate(namespace)
