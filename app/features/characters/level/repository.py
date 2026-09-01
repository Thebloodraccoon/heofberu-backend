"""Repository for the character max-level table (``character_max_levels``)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.repository import BaseRepository
from app.models.character_max_level_model import CharacterMaxLevel


class CharacterMaxLevelRepository(BaseRepository[CharacterMaxLevel]):
    """CRUD for ``character_max_levels`` (one row per character)."""

    def __init__(self, db: AsyncSession):
        """Create the max-level repository."""

        super().__init__(CharacterMaxLevel, db)

    async def get_by_character_id(self, character_id: int) -> CharacterMaxLevel | None:
        """Fetch the character's max-level row, or ``None`` if it has none."""

        result = await self.db.execute(select(CharacterMaxLevel).where(CharacterMaxLevel.character_id == character_id))
        return result.scalar_one_or_none()

    async def create_for_character(
        self,
        character_id: int,
        max_level: int,
        *,
        commit: bool = True,
    ) -> CharacterMaxLevel:
        """
        Seed a max-level row for a character.
        """

        row = CharacterMaxLevel(character_id=character_id, max_level=max_level)

        self.db.add(row)
        if commit:
            await self.db.commit()
            await self.db.refresh(row)
        else:
            await self.db.flush()

        return row