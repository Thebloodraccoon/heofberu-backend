"""Race ability-bonus service: full replacement of a race's bonuses."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.features.characters.progression.feature_sync import reconcile_characters_for_source
from app.features.races.cache import RACE_CACHE_NAMESPACES, invalidate_race_cache
from app.features.races.crud.repository import RaceRepository
from app.features.races.schemas import AbilityBonusesUpdate, RaceCreate, RaceResponse, RaceUpdate
from app.models.race_model import Race


class RaceAbilityBonusService(BaseService[Race, RaceCreate, RaceUpdate, RaceResponse, None]):
    """
    Full replacement of a race's ability score bonuses.

    Bonus changes reconcile affected characters via the one-way
    ``characters.progression.feature_sync`` import.
    """

    repository: RaceRepository

    cache_namespaces = RACE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize with a race repository and the race response schema."""

        super().__init__(
            repository=RaceRepository(db),
            response_schema=RaceResponse,
        )

    async def set_ability_bonuses(self, race_id: int, data: AbilityBonusesUpdate) -> RaceResponse:
        """Fully replace a race's ability score bonuses and refresh affected characters' stats."""

        race = await self._get_or_404(race_id)

        bonuses = [{"ability": item.ability, "bonus": item.bonus} for item in data.ability_bonuses]
        async with self._atomic():
            await self.repository.set_ability_bonuses(race, bonuses, commit=False)
            await reconcile_characters_for_source(self.repository.db, FeatureSourceType.RACE, race_id)
        await invalidate_race_cache()

        return await self._get_response(race_id)

    async def set_ability_bonuses_for_race(self, race: Race, bonuses: list[dict], *, commit: bool = True) -> None:
        """Replace a race's ability bonuses on an existing ``race`` row (used by ``create_race``)."""

        await self.repository.set_ability_bonuses(race, bonuses, commit=commit)
