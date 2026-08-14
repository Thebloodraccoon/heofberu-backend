"""Subclass cache coordination: one invalidation point shared by the subdomain's capabilities."""

from app.core.cache import invalidate

SUBCLASS_CACHE_NAMESPACES = ("classes", "nested_features")


async def invalidate_subclass_cache() -> None:
    """
    Purge every cache namespace a subclass read can hit.

    ``GET /classes/{id}`` (``classes``, which also embeds every subclass
    with its own SUBCLASS-source features) and the per-source feature
    listing (``nested_features``) are both served from cache. Any write to
    a subclass — base fields or its own features — must call this after
    its transaction commits, so the subdomain's capability services
    (crud/features) share a single invalidation point instead of each
    re-declaring the namespace tuple.
    """
    for namespace in SUBCLASS_CACHE_NAMESPACES:
        await invalidate(namespace)
