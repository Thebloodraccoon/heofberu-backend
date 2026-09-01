"""Race CRUD service: cached catalog CRUD plus composed capability reads."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.cached_service import CachedService
from app.features.features.crud.service import FeatureCrudService
from app.features.races.ability_bonuses.service import RaceAbilityBonusService
from app.features.races.cache import RACE_CACHE_NAMESPACES, invalidate_race_cache
from app.features.races.crud.repository import RaceRepository
from app.features.races.schemas import (
    RaceCreate,
    RaceGetAllResponse,
    RaceResponse,
    RaceUpdate,
)
from app.features.races.skills.service import RaceSkillService
from app.models.race_model import Race


class RaceCrudService(
    CachedService[Race, RaceCreate, RaceUpdate, RaceResponse, RaceGetAllResponse],
):
    """Race catalog CRUD with composed capability reads."""

    repository: RaceRepository

    cache_namespaces = RACE_CACHE_NAMESPACES
    get_all_order_by = "name"

    def __init__(self, db: AsyncSession):
        """Initialize composed skill, ability-bonus, and feature services."""

        super().__init__(
            repository=RaceRepository(db),
            response_schema=RaceResponse,
            get_all_schema=RaceGetAllResponse,
        )
        self._skills = RaceSkillService(db)
        self._ability_bonuses = RaceAbilityBonusService(db)
        self._features = FeatureCrudService(db)

    async def create_race(self, race_data: RaceCreate) -> RaceResponse:
        """Create a race, optionally seeding ability bonuses, skills, and features in one transaction."""

        skills = await self._skills.resolve_skills(race_data.granted_skills)

        payload = race_data.model_dump(exclude={"ability_bonuses", "granted_skills", "features"})

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

            if race_data.ability_bonuses:
                bonuses = [{"ability": b.ability, "bonus": b.bonus} for b in race_data.ability_bonuses]
                await self._ability_bonuses.set_ability_bonuses_for_race(item, bonuses, commit=False)

            if skills:
                await self._skills.set_skills_for_race(item, skills, commit=False)

            await self._features.create_features_for_source(
                FeatureSourceType.RACE,
                item.id,
                race_data.features,
                commit=False,
            )

        await invalidate_race_cache()

        return await self._get_response(item.id)
