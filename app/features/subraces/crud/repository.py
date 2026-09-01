"""Subrace repository: CRUD on ``Subrace`` rows, built on ``BaseRepository``."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models.subrace_association_models import SubraceAbilityBonus
from app.models.subrace_model import Subrace


class SubraceRepository(BaseRepository[Subrace]):
    """Repository for ``Subrace`` rows with eager-loaded ability bonuses."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with eager-loaded ability bonuses."""

        super().__init__(
            Subrace,
            db,
            default_load_options=[selectinload(Subrace.ability_bonuses)],
            search_fields=["name"],
        )

    async def list_for_race(self, race_id: int) -> list[Subrace]:
        """Return all subraces for ``race_id``, ordered by name."""

        return await self.get_all(filters={"race_id": race_id}, order_by=Subrace.name, limit=None)

    async def set_ability_bonuses(self, subrace: Subrace, bonuses: list[dict], *, commit: bool = True) -> Subrace:
        """Replace all ability bonuses for a subrace with the given list."""

        await self.replace_child_rows(
            SubraceAbilityBonus,
            subrace,
            "subrace_id",
            bonuses,
            commit=commit,
        )

        return subrace
