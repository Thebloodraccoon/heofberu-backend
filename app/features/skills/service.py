"""Skill CRUD service with in-use delete guard."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_service import BaseService, Page
from app.core.cache import use_cache
from app.features.skills.repository import SkillRepository
from app.features.skills.schemas import SkillCreate, SkillGetAllResponse, SkillResponse, SkillUpdate
from app.models.skill_model import Skill


class SkillService(BaseService[Skill, SkillCreate, SkillUpdate, SkillResponse, SkillGetAllResponse]):
    """
    Skill-specific CRUD service built on :class:`BaseService`.

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

    cache_namespaces = ("skills", "classes", "races", "backgrounds")

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=SkillRepository(db),
            response_schema=SkillResponse,
            get_all_schema=SkillGetAllResponse,
        )

    @use_cache()
    async def get_all(
        self,
        page: int = 1,
        size: int = 100,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
    ) -> Page[SkillGetAllResponse]:
        """Cached lightweight listing — see ``BaseService.get_all``."""

        return await super().get_all(page=page, size=size, filters=filters, search=search)

    @use_cache()
    async def get_by_id(self, item_id: int) -> SkillResponse:
        """Cached single-record fetch — see ``BaseService.get_by_id``."""

        return await super().get_by_id(item_id)
