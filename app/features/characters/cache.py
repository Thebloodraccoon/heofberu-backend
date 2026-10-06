"""Character cache coordination: exact-key invalidation per character_id."""

from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.transaction import after_commit
from app.core.cache import invalidate_many
from app.core.cache.client import cache_delete_key, cache_prefix

CHARACTER_CACHE_NAMESPACE = "characters"
CHARACTER_CACHE_TTL = 300
"""Seconds a cached response lives: bounds the staleness left by a cache-aside read racing an invalidation."""


def character_cache_key(character_id: int) -> str:
    """The exact Redis key of a character's cached response."""

    return f"{cache_prefix()}:{CHARACTER_CACHE_NAMESPACE}:{character_id}"


async def invalidate_character_cache(character_id: int, *, db: AsyncSession | None = None) -> None:
    """
    Drop the cached response of one character (a single exact-key delete).

    Pass the writing ``db`` session to defer the purge until the surrounding
    :func:`~app.core.base.transaction.atomic` block commits (dropped on
    rollback); without it the purge runs immediately.
    """

    async def _purge() -> None:
        await cache_delete_key(character_cache_key(character_id))

    if db is None:
        await _purge()
    else:
        await after_commit(db, _purge)


async def invalidate_characters_cache(character_ids: Iterable[int], *, db: AsyncSession | None = None) -> None:
    """
    Drop the cached responses of many characters over one Redis connection —
    for a single write that touches many characters at once (a GM
    feature/ability-bonus edit reconciling every character of a class).
    ``db`` defers the purge like in :func:`invalidate_character_cache`.
    """

    keys = [character_cache_key(character_id) for character_id in dict.fromkeys(character_ids)]
    if not keys:
        return

    async def _purge() -> None:
        await invalidate_many([], keys)

    if db is None:
        await _purge()
    else:
        await after_commit(db, _purge)
