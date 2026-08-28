"""Subrace ability-bonus service: full replacement of a subrace's bonuses."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
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
    """
    Everything about a subrace's ability score bonuses.

    ``set_ability_bonuses`` is the public full-replace write; the
    ``commit=False`` variant is shared with ``create_subrace`` so bonuses
    seed in the same transaction as the subrace row. Any write purges the
    ``races``, ``subrace_features`` and ``features`` namespaces via
    :func:`invalidate_subrace_cache`.
    """

    repository: SubraceRepository

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=SubraceRepository(db),
            response_schema=SubraceResponse,
        )

    async def set_ability_bonuses(self, subrace_id: int, data: SubraceAbilityBonusesUpdate) -> SubraceResponse:
        """Fully replace a subrace's ability score bonuses."""

        subrace = await self._get_or_404(subrace_id)

        bonuses = [{"ability": item.ability, "bonus": item.bonus} for item in data.ability_bonuses]
        await self.repository.set_ability_bonuses(subrace, bonuses)
        await invalidate_subrace_cache()

        return SubraceResponse.model_validate(await self._get_or_404(subrace_id))

    async def set_ability_bonuses_for_subrace(
        self, subrace: Subrace, bonuses: list[dict], *, commit: bool = True
    ) -> None:
        """Replace a subrace's bonuses on an existing ``subrace`` row (used by ``create_subrace``)."""

        await self.repository.set_ability_bonuses(subrace, bonuses, commit=commit)
