"""Subrace repository: CRUD on ``Subrace`` rows, built on ``BaseRepository``."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.core.exceptions import RecordAlreadyExistsError
from app.models.character_model import Character
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
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    async def _check_uniqueness(self, data: dict[str, Any], exclude_id: int | None = None) -> None:
        """Raise ``RecordAlreadyExistsError`` if a sibling subrace with the same name already exists."""

        if not self._unique_fields:
            return

        for field in self._unique_fields:
            if field in data and data[field] is not None:
                value = data[field]
                stmt = select(self.model.id).where(getattr(self.model, field) == value)

                race_id = data.get("race_id")
                if race_id is not None:
                    stmt = stmt.where(self.model.race_id == race_id)

                if exclude_id is not None:
                    stmt = stmt.where(self.model.id != exclude_id)

                if await self.db.scalar(stmt) is not None:
                    raise RecordAlreadyExistsError(model_name=self.model.__name__, field=field, value=value)

    async def is_in_use(self, subrace_id: int) -> bool:
        """Check whether any character references this subrace (blocks deletion)."""

        return await self.exists_referencing(Character, "subrace_id", subrace_id)

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
