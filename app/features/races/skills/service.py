"""Race granted-skill service: full replacement and id resolution."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.races.cache import RACE_CACHE_NAMESPACES
from app.features.races.schemas import RaceCreate, RaceResponse, RaceUpdate
from app.features.races.skills.repository import RaceSkillsRepository
from app.features.shared.skills.mixins import SkillsManagerMixin
from app.models.race_model import Race
from app.models.skill_model import Skill


class RaceSkillService(
    SkillsManagerMixin,
    BaseService[Race, RaceCreate, RaceUpdate, RaceResponse, None],
):
    """Full replacement and id-resolution for a race's granted skills."""

    repository: RaceSkillsRepository

    cache_namespaces = RACE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize with a race skills repository and the race response schema."""

        super().__init__(
            repository=RaceSkillsRepository(db),
            response_schema=RaceResponse,
        )

    async def resolve_skills(self, skill_ids: list[int] | None) -> list[Skill] | None:
        """Resolve ``skill_ids`` to ``Skill`` rows, or ``None`` when absent/empty."""

        return await self._resolve_skills(skill_ids)

    async def set_skills_for_race(self, race: Race, skills: list[Skill], *, commit: bool = True) -> None:
        """Attach ``skills`` to an existing ``race`` row (used by ``create_race``)."""

        await self.repository.set_skills(race, skills, commit=commit)
