"""Character cache coordination: point invalidation per character_id."""

from app.core.cache import invalidate
from app.core.cache.client import cache_delete_key, cache_prefix

CHARACTER_CACHE_NAMESPACE = "characters"


async def invalidate_character_cache(character_id: int) -> None:
    """
    Purge cached data for one character.

    ``GET /characters/{id}`` is cached under the flat key
    ``<prefix>:characters:<id>`` (custom ``key_builder``), which the
    namespace-prefix pattern ``<prefix>:characters:<id>:*`` never
    matches — so the exact key is deleted explicitly as well.
    """

    await invalidate(f"{CHARACTER_CACHE_NAMESPACE}:{character_id}")
    await cache_delete_key(f"{cache_prefix()}:{CHARACTER_CACHE_NAMESPACE}:{character_id}")