"""Skill cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

SKILL_CACHE_NAMESPACES = ("skills", "classes", "races", "backgrounds")


async def invalidate_skill_cache() -> None:
    """Purge every cache namespace a skill read can hit."""

    for namespace in SKILL_CACHE_NAMESPACES:
        await invalidate(namespace)
