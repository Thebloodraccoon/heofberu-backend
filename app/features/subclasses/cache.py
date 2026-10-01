"""Subclass cache coordination: the namespaces each kind of subclass write must purge."""

from app.core.cache import invalidate
from app.core.cache.namespaces import dependents

# ``classes`` holds the subclass detail and the class reads that embed subclass rows.
SUBCLASS_CACHE_NAMESPACES = ("classes",)

# Subclass create/rename/delete: spell reads embed subclass names (``available_subclasses``).
SUBCLASS_CRUD_CACHE_NAMESPACES = SUBCLASS_CACHE_NAMESPACES + dependents("subclasses")

# Deleting a subclass cascades to its features (``subclass_features`` list, central ``features``) and spell availability.
SUBCLASS_DELETE_CACHE_NAMESPACES = ("classes", "subclass_features", "features", *dependents("subclasses"))


async def invalidate_subclass_cache(*namespaces: str) -> None:
    """Purge ``namespaces`` (default: :data:`SUBCLASS_CACHE_NAMESPACES`)."""

    for namespace in namespaces or SUBCLASS_CACHE_NAMESPACES:
        await invalidate(namespace)
