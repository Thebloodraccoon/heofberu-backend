"""Race cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

# Character payloads derive ``speed`` live from the race at response time,
# so a race write must also purge cached character detail payloads.
# ``race_features`` is the race's own feature-list cache; ``features`` is
# the central by-id feature cache (``GET /features/{id}`` can now serve
# source-owned features).
RACE_CACHE_NAMESPACES = ("races", "race_features", "features", "characters")


async def invalidate_race_cache() -> None:
    """
    Purge every cache namespace a race read can hit.

    ``GET /races`` and ``GET /races/{id}`` (``races``, which also embeds
    the race's subraces), the race's own feature listing
    (``race_features``) and the central feature by-id cache (``features``)
    are all served from cache. Any write to a race — base fields, ability
    bonuses, granted skills, its own features, or a subrace — must call
    this after its transaction commits, so the capability services
    (crud/features/skills/ability_bonuses) share a single invalidation
    point instead of each re-declaring the namespace tuple.
    """

    for namespace in RACE_CACHE_NAMESPACES:
        await invalidate(namespace)
