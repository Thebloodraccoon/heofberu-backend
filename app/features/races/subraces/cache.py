"""Subrace cache coordination: one invalidation point shared by the subdomain's capabilities."""

from app.core.cache import invalidate

SUBRACE_CACHE_NAMESPACES = ("races", "nested_features")


async def invalidate_subrace_cache() -> None:
    """

    Purge every cache namespace a subrace read can hit.

    ``GET /races`` and ``GET /races/{id}`` (``races``, which also embeds
    every subrace) and the per-source feature listing (``nested_features``)
    are both served from cache. Any write to a subrace — base fields,
    ability bonuses, or its own features — must call this after its
    transaction commits, so the subdomain's capability services
    (crud/features/ability_bonuses) share a single invalidation point
    instead of each re-declaring the namespace tuple.
    """

    for namespace in SUBRACE_CACHE_NAMESPACES:
        await invalidate(namespace)
