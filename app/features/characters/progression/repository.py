"""Repository for the character ASI-level choices audit table."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import ASILevelChoice
from app.core.base.repository import BaseRepository
from app.models.character_asi_choice_model import CharacterASIChoice, CharacterASIChoiceIncrease


class CharacterASIChoiceRepository(BaseRepository[CharacterASIChoice]):
    """CRUD for ``character_asi_choices`` (one row per resolved ASI level)."""

    def __init__(self, db: AsyncSession):
        super().__init__(CharacterASIChoice, db)

    async def get_character_choices(self, character_id: int) -> list[CharacterASIChoice]:
        """List a character's resolved ASI-level choices, ordered by level."""

        result = await self.db.execute(
            select(CharacterASIChoice)
            .where(CharacterASIChoice.character_id == character_id)
            .options(selectinload(CharacterASIChoice.increases))
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
        or ``None`` for a GM adjustment from the GM panel.
        ``increases`` holds the ASI increments as
        ``[{"ability": "STR", "amount": 2}]`` and is written as typed
        ``CharacterASIChoiceIncrease`` child rows — these are the rows the
        ability-score calculator counts (only ``choice_type == ASI``
        carries them); ``feat_id`` / ``ability_score_increase_id`` are set
        for ``FEAT`` choices, whose stat effect flows through the granted
        ``character_feats`` row instead. New choices are always recorded
        with ``applied_to_base = False``: the base columns are never
        touched, the log IS the counted source. ``commit=False`` defers
        the commit for callers wrapping the write in a transaction.
        """

        row = CharacterASIChoice(
            character_id=character_id,
            class_level=class_level,
            choice_type=choice_type,
            feat_id=feat_id,
            ability_score_increase_id=ability_score_increase_id,
            applied_to_base=False,
        )

        for item in increases or []:
            row.increases.append(CharacterASIChoiceIncrease(ability=item["ability"], amount=item["amount"]))

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
            select(CharacterASIChoice)
            .where(
                CharacterASIChoice.id == choice_id,
                CharacterASIChoice.character_id == character_id,
            )
            .options(selectinload(CharacterASIChoice.increases))
        )
        return result.scalar_one_or_none()

    async def remove_choice(self, choice: CharacterASIChoice) -> bool:
        """
        Delete a choice row together with its increment children (the
        cascade removes them). Since counted points live ONLY in these
        rows, deletion is all it takes to revert an adjustment's stat
        effect — the caller just refreshes the ability-score cache.
        """

        await self.db.delete(choice)
        await self.db.commit()
        return True
