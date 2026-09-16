"""Character cache coordination: point invalidation per character_id."""

from collections.abc import Iterable

from app.core.cache import invalidate, invalidate_many
from app.core.cache.client import cache_delete_key, cache_prefix

CHARACTER_CACHE_NAMESPACE = "characters"


async def invalidate_character_cache(character_id: int) -> None:
    """
    Purge cached data for one character, including the flat detail key.
    """

    await invalidate(f"{CHARACTER_CACHE_NAMESPACE}:{character_id}")
    await cache_delete_key(f"{cache_prefix()}:{CHARACTER_CACHE_NAMESPACE}:{character_id}")


async def invalidate_characters_cache(character_ids: Iterable[int]) -> None:
    """
    Purge cached data for many characters in one Redis connection/``DEL``
    instead of looping :func:`invalidate_character_cache` — use this when a
    single write affects many characters at once (a GM feature/ability-bonus
    edit reconciling every character of that class/race/etc.).
    """

    ids = list(dict.fromkeys(character_ids))
    if not ids:
        return

    namespaces = [f"{CHARACTER_CACHE_NAMESPACE}:{character_id}" for character_id in ids]
    flat_keys = [f"{cache_prefix()}:{CHARACTER_CACHE_NAMESPACE}:{character_id}" for character_id in ids]
    await invalidate_many(namespaces, flat_keys)
