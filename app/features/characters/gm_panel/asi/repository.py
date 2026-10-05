"""GM ASI-adjustment repository: the ``class_level IS NULL`` rows of ``character_asi_choices``."""

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.features.characters.progression.repository import CharacterASIChoiceRepository
from app.models.character.character_asi_choice_model import CharacterASIChoice


class GmAsiRepository(CharacterASIChoiceRepository):
    """Level-free GM adjustments on top of the shared ASI-choice repository; writes only flush."""

    async def get_adjustments(self, character_id: int) -> list[CharacterASIChoice]:
        """The character's GM adjustments (no class level), oldest first, with their increases."""

        result = await self.db.execute(
            select(CharacterASIChoice)
            .where(CharacterASIChoice.character_id == character_id, CharacterASIChoice.class_level.is_(None))
            .options(selectinload(CharacterASIChoice.increases))
            .order_by(CharacterASIChoice.id)
        )
        return list(result.scalars().unique().all())

    async def delete_adjustment(self, choice: CharacterASIChoice) -> None:
        """Delete one adjustment row (its increases cascade); the caller's atomic block commits."""

        await self.db.delete(choice)
        await self.db.flush()
