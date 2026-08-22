"""Skill CRUD service with in-use delete guard."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.features.skills.cache import SKILL_CACHE_NAMESPACES
from app.features.skills.crud.repository import SkillRepository
from app.features.skills.crud.schemas import SkillCreate, SkillGetAllResponse, SkillResponse, SkillUpdate
from app.models import Skill


class SkillCrudService(CachedService[Skill, SkillCreate, SkillUpdate, SkillResponse, SkillGetAllResponse]):
    """
    Skill-specific CRUD service built on :class:`CachedService`.

    Adds behaviors the generic base class doesn't provide:
      - a uniqueness check on ``key`` before create/update;
      - a delete guard that blocks removing a skill still referenced by any
        race, class, background, or character skill proficiency, since the
        FK on all four is ``ON DELETE RESTRICT``.

    The listing and detail reads are cached via ``@use_cache``. Besides
    the ``skills`` namespace, writes also purge ``classes``/``races``/
    ``backgrounds``: their cached detail responses embed skills
    (``SkillResponse``), so a skill rename must not leave stale names in
    the class/race/background cache.
    """

    repository: SkillRepository

    cache_namespaces = SKILL_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=SkillRepository(db),
            response_schema=SkillResponse,
            get_all_schema=SkillGetAllResponse,
        )
