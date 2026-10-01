"""Race cache namespaces: what each kind of write has to purge."""

from app.core.cache import invalidate_many
from app.core.cache.namespaces import dependents

# Race reads, and the subrace reads, which share the ``races`` namespace.
RACE_CACHE_NAMESPACES = ("races",)

# Race create/rename/delete: spell reads embed race names (``available_races``).
RACE_CRUD_CACHE_NAMESPACES = RACE_CACHE_NAMESPACES + dependents("races")

# Deleting a race cascades to its features, its subraces' features and spell availability.
RACE_DELETE_NAMESPACES = ("races", "race_features", "subrace_features", "features", *dependents("races"))


async def invalidate_race_cache() -> None:
    """Purge the race read namespace (image changes)."""

    await invalidate_many(list(RACE_CACHE_NAMESPACES))
