"""Subrace repository: CRUD on ``Subrace`` rows, built on ``BaseRepository``."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.core.exceptions import RecordAlreadyExistsError
from app.features.features.crud.repository import feature_summary_loads
from app.models.character.character_model import Character
from app.models.races.race_model import Race
from app.models.races.subrace_association_models import SubraceAbilityBonus
from app.models.races.subrace_model import Subrace


class SubraceRepository(BaseRepository[Subrace]):
    """Repository for ``Subrace`` rows with eager-loaded ability bonuses, tags and features."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with eager-loaded ability bonuses, tags and features."""

        super().__init__(
            Subrace,
            db,
            default_load_options=[
                selectinload(Subrace.ability_bonuses),
                selectinload(Subrace.tags),
                *feature_summary_loads(selectinload(Subrace.features)),
            ],
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    async def _check_uniqueness(self, data: dict[str, Any], exclude_id: int | None = None) -> None:
        """
        Raise ``RecordAlreadyExistsError`` if a sibling subrace already has the name.

        Names are unique per race (``uq_subrace_race_id_name``). The race comes
        from ``data`` on create, and from the row being updated (``exclude_id``)
        on a rename, whose payload carries no ``race_id``.
        """

        name = data.get("name")
        if name is None:
            return

        stmt = select(Subrace.id).where(Subrace.name == name)

        race_id = data.get("race_id")
        if race_id is not None:
            stmt = stmt.where(Subrace.race_id == race_id)
        elif exclude_id is not None:
            own_race = select(Subrace.race_id).where(Subrace.id == exclude_id).scalar_subquery()
            stmt = stmt.where(Subrace.race_id == own_race)

        if exclude_id is not None:
            stmt = stmt.where(Subrace.id != exclude_id)

        if await self.db.scalar(stmt) is not None:
            raise RecordAlreadyExistsError(model_name=self.model.__name__, field="name", value=name)

    async def race_exists(self, race_id: int) -> bool:
        """Whether a race with ``race_id`` exists."""

        return await self.db.scalar(select(Race.id).where(Race.id == race_id)) is not None

    async def is_in_use(self, subrace_id: int) -> bool:
        """Check whether any character references this subrace (blocks deletion)."""

        return await self.exists_referencing(Character, "subrace_id", subrace_id)

    async def list_for_race(self, race_id: int) -> list[Any]:
        """
        Return brief ``(id, race_id, name, image_url)`` rows for ``race_id``, ordered by name.

        Column-select on purpose: ``default_load_options`` eager-loads
        ``ability_bonuses`` plus the full feature effect tree
        (``feature_summary_loads``), which ``SubraceGetAllResponse`` never
        uses. Going through ``get_all`` here would pay for both on every
        row of every listing.
        """

        return await self.get_brief(
            Subrace.id,
            Subrace.race_id,
            Subrace.name,
            Subrace.image_url,
            filters={"race_id": race_id},
            order_by=Subrace.name,
            limit=None,
        )

    async def set_ability_bonuses(self, subrace_id: int, bonuses: list[dict]) -> None:
        """Replace all ability bonuses for a subrace with the given list."""

        await self.replace_child_rows(
            SubraceAbilityBonus,
            Subrace(id=subrace_id),
            "subrace_id",
            bonuses,
        )
