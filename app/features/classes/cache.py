"""Class cache coordination: the namespaces each kind of class write must purge."""

from app.core.cache import invalidate
from app.core.cache.namespaces import dependents

# Class detail/listing/progression and the subclass detail all live under ``classes``.
# Cached character payloads only depend on a class's ``hit_dice`` (purged per character
# by ``ClassCrudService.update_class`` when it changes), so ``characters`` is not here.
CLASS_CACHE_NAMESPACES = ("classes",)

# Class create/rename/delete: spell reads embed class names (``available_classes``).
CLASS_CRUD_CACHE_NAMESPACES = CLASS_CACHE_NAMESPACES + dependents("classes")

# Starting equipment is also cached per source under ``nested_items``.
CLASS_ITEMS_CACHE_NAMESPACES = ("classes", "nested_items")

# Deleting a class cascades to its subclasses, features, starting items and spell availability rows.
CLASS_DELETE_CACHE_NAMESPACES = (
    "classes",
    "class_features",
    "subclass_features",
    "features",
    "nested_items",
    *dependents("classes"),
)


async def invalidate_class_cache(*namespaces: str) -> None:
    """Purge ``namespaces`` (default: :data:`CLASS_CACHE_NAMESPACES`)."""

    for namespace in namespaces or CLASS_CACHE_NAMESPACES:
        await invalidate(namespace)
