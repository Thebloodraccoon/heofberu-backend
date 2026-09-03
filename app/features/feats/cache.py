"""Feat cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

FEAT_CACHE_NAMESPACES = ("feats",)


async def invalidate_feat_cache() -> None:
    """
    Purge every cache namespace a feat read can hit.

    Feats own no features (a feat is de facto its own feature — the
    content lives in its description), so only the ``feats`` namespace
    is served from cache.
    """

    for namespace in FEAT_CACHE_NAMESPACES:
        await invalidate(namespace)
