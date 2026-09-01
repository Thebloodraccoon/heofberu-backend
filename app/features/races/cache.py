"""Race cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

# Characters derive ``speed`` from the race, so race writes must also purge
# cached character payloads.  ``race_features`` is the race's own feature
# listing; ``features`` is the central by-id feature cache.
RACE_CACHE_NAMESPACES = ("races", "race_features", "features", "characters")


async def invalidate_race_cache() -> None:
    """Purge every cache namespace a race read can hit."""

    for namespace in RACE_CACHE_NAMESPACES:
        await invalidate(namespace)
