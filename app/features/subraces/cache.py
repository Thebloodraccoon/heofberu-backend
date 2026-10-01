"""Subrace cache namespaces: what each kind of write has to purge."""

from app.core.cache import invalidate_many
from app.core.cache.namespaces import dependents

# Subrace reads share the race namespace: a race detail embeds its subraces.
SUBRACE_CACHE_NAMESPACES = ("races",)

# Subrace create/rename/delete: spell reads embed subrace names (``available_subraces``).
SUBRACE_CRUD_CACHE_NAMESPACES = SUBRACE_CACHE_NAMESPACES + dependents("subraces")

# Deleting a subrace cascades to its features and spell availability.
SUBRACE_DELETE_NAMESPACES = ("races", "subrace_features", "features", *dependents("subraces"))


async def invalidate_subrace_cache() -> None:
    """Purge the subrace read namespace (image changes)."""

    await invalidate_many(list(SUBRACE_CACHE_NAMESPACES))
