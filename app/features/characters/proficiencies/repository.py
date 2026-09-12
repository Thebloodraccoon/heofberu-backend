"""Character proficiency repository: read-only query across every ``character_proficiencies`` row."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.character.character_proficiency_model import CharacterProficiency


class CharacterProficiencyRepository:
    """Read-only queries for a character's proficiency rows (every kind, every source)."""

    def __init__(self, db: AsyncSession):
        """Create the repository over the shared session."""

        self.db = db

    async def get_all(self, character_id: int) -> list[CharacterProficiency]:
        """
        Every proficiency row for the character, across every kind and
        source, with the granting reference ``Feature`` eager-loaded for
        provenance (``feature_name`` in the response).
        """

        result = await self.db.execute(
            select(CharacterProficiency)
            .options(selectinload(CharacterProficiency.feature))
            .where(CharacterProficiency.character_id == character_id)
        )
        return list(result.scalars().unique().all())
