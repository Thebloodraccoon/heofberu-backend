"""Tag cache coordination: one invalidation point shared by every capability.

Every catalog that embeds tags (races/subraces/backgrounds/articles) reads
them through ITS OWN cache namespace, not this one — a tag write only needs
to purge the tag dictionary's own listing plus those namespaces, mirroring
how ``skills`` purges the catalogs it's granted through. Subraces cache
under the ``"races"`` namespace too (see ``SUBRACE_CACHE_NAMESPACES`` in
``app/features/subraces/cache.py``) — there is no separate ``"subraces"``
namespace to purge.
"""

from app.core.cache import invalidate

TAG_CACHE_NAMESPACES = ("tags", "races", "backgrounds", "articles")


async def invalidate_tag_cache() -> None:
    """Purge every cache namespace a tag read can hit."""

    for namespace in TAG_CACHE_NAMESPACES:
        await invalidate(namespace)
