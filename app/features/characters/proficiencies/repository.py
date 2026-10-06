"""Character proficiency repository: read-only query across every ``character_proficiencies`` row."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character.character_proficiency_model import CharacterProficiency


class CharacterProficiencyRepository:
    """Read-only queries for a character's stored proficiency rows (class/race/background choices, GM overrides)."""

    def __init__(self, db: AsyncSession):
        """Create the repository over the shared session."""

        self.db = db

    async def get_all(self, character_id: int) -> list[CharacterProficiency]:
        """Every stored proficiency row for the character, across every kind and source."""

        result = await self.db.execute(
            select(CharacterProficiency).where(CharacterProficiency.character_id == character_id)
        )
        return list(result.scalars().unique().all())
