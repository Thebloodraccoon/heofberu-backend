"""Repository for the character ASI-level choices audit table."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ASILevelChoice
from app.core.base_repository import BaseRepository
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
        class_level: int,
        choice_type: ASILevelChoice | str,
        *,
        feat_id: int | None = None,
        ability_score_increase_id: int | None = None,
        increases: list[dict] | None = None,
        commit: bool = True,
    ) -> CharacterASIChoice:
        """
        Record one resolved ASI-level choice.

        ``increases`` holds the ASI increments as ``[{"ability": "STR",
        "amount": 2}]`` (only for ``choice_type == ASI``); ``feat_id`` /
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
