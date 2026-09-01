"""Subrace cache coordination: one invalidation point shared by the subdomain's capabilities."""

from app.core.cache import invalidate

# ``subrace_features`` is the subrace's own feature listing; ``features``
# is the central by-id feature cache.  Character payloads embed
# ability-score totals derived from subrace bonuses, so subrace writes
# must also purge cached character payloads.
SUBRACE_CACHE_NAMESPACES = ("races", "subrace_features", "features", "characters")


async def invalidate_subrace_cache() -> None:
    """Purge every cache namespace a subrace read can hit."""

    for namespace in SUBRACE_CACHE_NAMESPACES:
        await invalidate(namespace)
