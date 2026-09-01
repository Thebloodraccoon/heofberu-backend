"""Skill CRUD service with in-use delete guard."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.features.skills.cache import SKILL_CACHE_NAMESPACES
from app.features.skills.crud.repository import SkillRepository
from app.features.skills.crud.schemas import SkillCreate, SkillGetAllResponse, SkillResponse, SkillUpdate
from app.models import Skill


class SkillCrudService(CachedService[Skill, SkillCreate, SkillUpdate, SkillResponse, SkillGetAllResponse]):
    """Skill-specific CRUD service. Adds a key-uniqueness check and an in-use delete guard."""

    repository: SkillRepository

    cache_namespaces = SKILL_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Wire up the skill repository, response schema, and get-all schema."""

        super().__init__(
            repository=SkillRepository(db),
            response_schema=SkillResponse,
            get_all_schema=SkillGetAllResponse,
        )
