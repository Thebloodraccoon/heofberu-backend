"""Class cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

# Character payloads serialize some class data LIVE at response time —
# ``saving_throw_proficiencies`` comes off ``character.character_class``
# and hit dice/speed derive from the class — so any class write must also
# purge the cached character detail payloads, or they go stale until TTL.
# ``class_features`` is the class's own feature-list cache; ``features`` is
# the central by-id feature cache (``GET /features/{id}`` can now serve
# source-owned features).
CLASS_CACHE_NAMESPACES = ("classes", "class_features", "features", "nested_items", "characters")


async def invalidate_class_cache() -> None:
    """
    Purge every cache namespace a class read can hit.

    ``GET /classes`` and ``GET /classes/{id}`` (``classes``, which also
    embeds the class's features and every subclass), the class's own
    feature listing (``class_features``), the central feature by-id cache
    (``features``), the per-source item listing (``nested_items``) and the
    cached character detail payloads (``characters`` — live-derived
    saves/hit dice) are all served from cache. Any write to a class — base
    fields, primary abilities, saving throws, armor proficiencies,
    available skills, starting items, spell slots, its own features, or a
    subclass — must call this after its transaction commits, so the
    capability services (crud/features/skills/items/armor/throws/
    progression) share a single invalidation point instead of each
    re-declaring the namespace tuple.
    """

    for namespace in CLASS_CACHE_NAMESPACES:
        await invalidate(namespace)
