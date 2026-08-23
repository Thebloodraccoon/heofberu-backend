"""Skill cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

SKILL_CACHE_NAMESPACES = ("skills", "classes", "races", "backgrounds")


async def invalidate_skill_cache() -> None:
    """
    Purge every cache namespace a skill read can hit.

    Besides the ``skills`` namespace, the class/race/background cached
    detail responses embed skills (``SkillResponse``), so a skill rename
    must not leave stale names in those caches. Any write to a skill must
    call this after its transaction commits.
    """

    for namespace in SKILL_CACHE_NAMESPACES:
        await invalidate(namespace)
