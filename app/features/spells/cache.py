"""Spell cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

SPELL_CACHE_NAMESPACES = ("spells",)


async def invalidate_spell_cache() -> None:
    """
    Purge every cache namespace a spell read can hit.

    ``GET /spells`` (``spells`` namespace) is served from cache. Any write
    to a spell — catalog CRUD via ``/spells`` or a class/race availability
    change — must call this after its transaction commits.
    """

    for namespace in SPELL_CACHE_NAMESPACES:
        await invalidate(namespace)
