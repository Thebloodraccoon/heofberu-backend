"""Race ability-bonus service: full replacement of a race's bonuses."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.races.cache import RACE_CACHE_NAMESPACES, invalidate_race_cache
from app.features.races.crud.repository import RaceRepository
from app.features.races.schemas import AbilityBonusesUpdate, RaceCreate, RaceResponse, RaceUpdate
from app.models.race_model import Race


class RaceAbilityBonusService(BaseService[Race, RaceCreate, RaceUpdate, RaceResponse, None]):
    """
    Everything about a race's ability score bonuses.

    ``set_ability_bonuses`` is the public full-replace write; the
    ``commit=False`` variant is shared with ``create_race`` so bonuses seed
    in the same transaction as the race row. Any write purges the ``races``
    and ``nested_features`` namespaces.
    """

    repository: RaceRepository

    cache_namespaces = RACE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=RaceRepository(db),
            response_schema=RaceResponse,
        )

    async def set_ability_bonuses(self, race_id: int, data: AbilityBonusesUpdate) -> RaceResponse:
        """Fully replace a race's ability score bonuses."""

        race = await self._get_or_404(race_id)

        bonuses = [{"ability": item.ability, "bonus": item.bonus} for item in data.ability_bonuses]
        await self.repository.set_ability_bonuses(race, bonuses)
        await invalidate_race_cache()

        return await self._get_response(race_id)

    async def set_ability_bonuses_for_race(self, race: Race, bonuses: list[dict], *, commit: bool = True) -> None:
        """Replace a race's ability bonuses on an existing ``race`` row (used by ``create_race``)."""

        await self.repository.set_ability_bonuses(race, bonuses, commit=commit)
