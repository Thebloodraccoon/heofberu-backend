"""Class cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

CLASS_CACHE_NAMESPACES = ("classes", "nested_features", "nested_items")


async def invalidate_class_cache() -> None:
    """
    Purge every cache namespace a class read can hit.

    ``GET /classes`` and ``GET /classes/{id}`` (``classes``, which also
    embeds the class's features and every subclass), the per-source feature
    listing (``nested_features``) and the per-source item listing
    (``nested_items``) are all served from cache. Any write to a class —
    base fields, primary abilities, saving throws, armor proficiencies,
    available skills, starting items, spell slots, its own features, or a
    subclass — must call this after its transaction commits, so the
    capability services (crud/features/skills/items/armor/throws/
    progression) share a single invalidation point instead of each
    re-declaring the namespace tuple.
    """
    for namespace in CLASS_CACHE_NAMESPACES:
        await invalidate(namespace)
