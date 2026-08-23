"""Race cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

# Character payloads derive ``speed`` live from the race at response time,
# so a race write must also purge cached character detail payloads.
RACE_CACHE_NAMESPACES = ("races", "nested_features", "characters")


async def invalidate_race_cache() -> None:
    """
    Purge every cache namespace a race read can hit.

    ``GET /races`` and ``GET /races/{id}`` (``races``, which also embeds
    the race's subraces) and the per-source feature listing
    (``nested_features``) are all served from cache. Any write to a race —
    base fields, ability bonuses, granted skills, its own features, or a
    subrace — must call this after its transaction commits, so the
    capability services (crud/features/skills/ability_bonuses) share a
    single invalidation point instead of each re-declaring the namespace
    tuple.
    """

    for namespace in RACE_CACHE_NAMESPACES:
        await invalidate(namespace)
