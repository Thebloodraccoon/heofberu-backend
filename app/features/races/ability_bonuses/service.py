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
    Everything about a race's ability score bonuses.

    ``set_ability_bonuses`` is the public full-replace write; the
    ``commit=False`` variant is shared with ``create_race`` so bonuses seed
    in the same transaction as the race row. Any write purges the ``races``,
    ``race_features``, ``features`` and ``characters`` namespaces.

    A bonus change also flows into every existing character of that race:
    the write reconciles the affected characters via the known one-way
    ``characters.progression.feature_sync`` import, so their
    ``character_ability_scores`` cache rows (and per-character Redis
    payloads) refresh in the same transaction instead of staying stale
    until a GM-panel read recomputes them.
    """

    repository: RaceRepository

    cache_namespaces = RACE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
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
