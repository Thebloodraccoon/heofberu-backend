"""Subrace ability-bonus service: full replacement of a subrace's bonuses."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.features.characters.progression.feature_sync import reconcile_characters_for_source
from app.features.subraces.cache import invalidate_subrace_cache
from app.features.subraces.crud.repository import SubraceRepository
from app.features.subraces.crud.schemas import (
    SubraceAbilityBonusesUpdate,
    SubraceCreate,
    SubraceResponse,
    SubraceUpdate,
)
from app.models.subrace_model import Subrace


class SubraceAbilityBonusService(
    BaseService[Subrace, SubraceCreate, SubraceUpdate, SubraceResponse, None],
):
    """Full replacement of a subrace's ability score bonuses.

    Bonus changes reconcile affected characters via the one-way
    ``characters.progression.feature_sync`` import.
    """

    repository: SubraceRepository

    def __init__(self, db: AsyncSession):
        """Initialize with a subrace repository and the subrace response schema."""

        super().__init__(
            repository=SubraceRepository(db),
            response_schema=SubraceResponse,
        )

    async def set_ability_bonuses(self, subrace_id: int, data: SubraceAbilityBonusesUpdate) -> SubraceResponse:
        """Fully replace a subrace's ability score bonuses and refresh affected characters' stats."""

        subrace = await self._get_or_404(subrace_id)

        bonuses = [{"ability": item.ability, "bonus": item.bonus} for item in data.ability_bonuses]
        async with self._atomic():
            await self.repository.set_ability_bonuses(subrace, bonuses, commit=False)
            await reconcile_characters_for_source(self.repository.db, FeatureSourceType.SUBRACE, subrace_id)
        await invalidate_subrace_cache()

        return SubraceResponse.model_validate(await self._get_or_404(subrace_id))

    async def set_ability_bonuses_for_subrace(
        self, subrace: Subrace, bonuses: list[dict], *, commit: bool = True
    ) -> None:
        """Replace a subrace's bonuses on an existing ``subrace`` row (used by ``create_subrace``)."""

        await self.repository.set_ability_bonuses(subrace, bonuses, commit=commit)
