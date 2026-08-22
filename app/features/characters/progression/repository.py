"""Repository for the character ASI-level choices audit table."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ASILevelChoice
from app.core.base.repository import BaseRepository
from app.models.character_asi_choice_model import CharacterASIChoice


class CharacterASIChoiceRepository(BaseRepository[CharacterASIChoice]):
    """CRUD for ``character_asi_choices`` (one row per resolved ASI level)."""

    def __init__(self, db: AsyncSession):
        super().__init__(CharacterASIChoice, db)

    async def get_character_choices(self, character_id: int) -> list[CharacterASIChoice]:
        """List a character's resolved ASI-level choices, ordered by level."""

        result = await self.db.execute(
            select(CharacterASIChoice)
            .where(CharacterASIChoice.character_id == character_id)
            .order_by(CharacterASIChoice.class_level)
        )
        return list(result.scalars().unique().all())

    async def add(
        self,
        character_id: int,
        class_level: int | None,
        choice_type: ASILevelChoice | str,
        *,
        feat_id: int | None = None,
        ability_score_increase_id: int | None = None,
        increases: list[dict] | None = None,
        commit: bool = True,
    ) -> CharacterASIChoice:
        """
        Record one resolved ASI-level choice.

        ``class_level`` is the ASI class level for level-up resolutions,
        or ``None`` for a GM adjustment from the GM panel. ``increases``
        holds the ASI increments as ``[{"ability": "STR", "amount": 2}]``
        (only for ``choice_type == ASI``); ``feat_id`` /
        ``ability_score_increase_id`` are set for ``FEAT`` choices.
        ``commit=False`` defers the commit for callers wrapping the write
        in a transaction.
        """

        row = CharacterASIChoice(
            character_id=character_id,
            class_level=class_level,
            choice_type=choice_type,
            feat_id=feat_id,
            ability_score_increase_id=ability_score_increase_id,
            increases=increases,
        )

        self.db.add(row)
        if commit:
            await self.db.commit()
            await self.db.refresh(row)
        else:
            await self.db.flush()

        return row

    async def get_choice_by_id(self, character_id: int, choice_id: int) -> CharacterASIChoice | None:
        """Fetch one choice row by its own id, scoped to the character."""

        result = await self.db.execute(
            select(CharacterASIChoice).where(
                CharacterASIChoice.id == choice_id,
                CharacterASIChoice.character_id == character_id,
            )
        )
        return result.scalar_one_or_none()

    async def remove_choice(self, choice: CharacterASIChoice) -> bool:
        """Delete a choice row (GM adjustment removal; caller reverts the stat bumps)."""

        await self.db.delete(choice)
        await self.db.commit()
        return True
