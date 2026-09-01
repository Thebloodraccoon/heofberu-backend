"""Background granted-skill service: full replacement and id resolution."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.backgrounds.cache import BACKGROUND_CACHE_NAMESPACES
from app.features.backgrounds.crud.schemas import BackgroundCreate, BackgroundResponse, BackgroundUpdate
from app.features.backgrounds.skills.repository import BackgroundSkillsRepository
from app.features.shared.skills.mixins import SkillsManagerMixin
from app.models import Background, Skill

class BackgroundSkillsService(
    SkillsManagerMixin,
    BaseService[Background, BackgroundCreate, BackgroundUpdate, BackgroundResponse, None],
):
    """
    Background granted-skill service: full replacement and skill-id resolution.

    ``set_skills`` and skill-id resolution come from :class:`SkillsManagerMixin`;
    generic CRUD machinery comes from :class:`BaseService`.
    """

    repository: BackgroundSkillsRepository

    cache_namespaces = BACKGROUND_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize the service with the skills repository."""

        super().__init__(
            repository=BackgroundSkillsRepository(db),
            response_schema=BackgroundResponse,
        )

    async def resolve_skills(self, skill_ids: list[int] | None) -> list[Skill] | None:
        """Resolve ``skill_ids`` to ``Skill`` rows, or ``None`` when absent/empty."""

        return await self._resolve_skills(skill_ids)

    async def set_skills_for_background(
        self, background: Background, skills: list[Skill], *, commit: bool = True
    ) -> None:
        """Attach ``skills`` to an existing ``background`` row (used by ``create_background``)."""

        await self.repository.set_skills(background, skills, commit=commit)
