"""Skill CRUD service with in-use delete guard."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.core.base.transaction import invalidate_after_commit
from app.features.skills.cache import SKILL_CACHE_NAMESPACES, SKILL_OWN_CACHE_NAMESPACES
from app.features.skills.crud.repository import SkillRepository
from app.features.skills.crud.schemas import SkillCreate, SkillGetAllResponse, SkillResponse, SkillUpdate
from app.models import Skill


class SkillCrudService(CachedService[Skill, SkillCreate, SkillUpdate, SkillResponse, SkillGetAllResponse]):
    """
    Skill CRUD with a name-uniqueness check and an in-use delete guard.

    Updates purge every namespace that embeds skill names; create and delete
    only touch the skill listings (see :mod:`app.features.skills.cache`).
    """

    repository: SkillRepository

    cache_namespaces = SKILL_CACHE_NAMESPACES
    get_all_order_by = "name"

    def __init__(self, db: AsyncSession):
        """Wire up the skill repository, response schema, and get-all schema."""

        super().__init__(
            repository=SkillRepository(db),
            response_schema=SkillResponse,
            get_all_schema=SkillGetAllResponse,
        )

    async def create(self, create_data: SkillCreate) -> SkillResponse:
        """Create a skill; nothing references it yet, so only the skill listings are purged."""

        async with self._atomic():
            item = await self.repository.create(create_data.model_dump())
            await invalidate_after_commit(self.repository.db, *SKILL_OWN_CACHE_NAMESPACES)

        return self.response_schema.model_validate(item)

    async def delete(self, item_id: int) -> bool:
        """Delete an unused skill; only the skill listings can hold it."""

        item = await self._get_or_404(item_id)
        async with self._atomic():
            result = await self.repository.delete(item)
            await invalidate_after_commit(self.repository.db, *SKILL_OWN_CACHE_NAMESPACES)

        return result
