"""Class cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

# Character payloads serialize some class data live at response time
# (``saving_throw_proficiencies``, hit dice/speed derive from the class),
# so class writes must also purge the cached character payloads.
CLASS_CACHE_NAMESPACES = ("classes", "class_features", "features", "nested_items", "characters")


async def invalidate_class_cache() -> None:
    """Purge every cache namespace a class read can hit."""

    for namespace in CLASS_CACHE_NAMESPACES:
        await invalidate(namespace)
