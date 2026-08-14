"""Subrace repository: CRUD on ``Subrace`` rows, built on ``BaseRepository``."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models.subrace_association_models import SubraceAbilityBonus
from app.models.subrace_model import Subrace


class SubraceRepository(BaseRepository[Subrace]):
    """
    ``BaseRepository``-backed repository for ``Subrace`` rows.

    ``ability_bonuses`` are always part of ``SubraceResponse``, so they're
    wired up as ``default_load_options`` rather than re-implemented here.
    ``race_id`` scoping (a subrace always belongs to exactly one race) is
    handled by the service layer via an explicit ownership check — the
    repository itself stays a plain single-model CRUD surface, same shape
    as ``SubclassRepository``.
    """

    def __init__(self, db: AsyncSession):
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
        """
        Replace all ability bonuses for a subrace with the given list.

        ``commit`` lets callers that need atomicity across multiple writes
        (e.g. creating a subrace + its bonuses together) defer the commit
        and flush instead, without duplicating this method.
        """

        await self.replace_child_rows(
            SubraceAbilityBonus,
            subrace,
            "subrace_id",
            bonuses,
            commit=commit,
        )

        return subrace
