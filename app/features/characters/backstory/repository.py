"""Character backstory repository: single-row get/upsert (uncached)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.repository import BaseRepository
from app.models.character_backstory_model import CharacterBackstory


class CharacterBackstoryRepository(BaseRepository[CharacterBackstory]):
    """Repository for a character's backstory (``character_backstories``, one row per character)."""

    def __init__(self, db: AsyncSession):
        """Create the backstory repository."""

        super().__init__(CharacterBackstory, db)

    async def get_for_character(self, character_id: int) -> CharacterBackstory | None:
        """Fetch a character's backstory row, if one exists."""

        result = await self.db.execute(
            select(CharacterBackstory).where(CharacterBackstory.character_id == character_id)
        )
        return result.scalar_one_or_none()

    async def upsert_content(self, character_id: int, content: str) -> CharacterBackstory:
        """Create the backstory row if missing, else replace its content, and commit."""

        row = await self.get_for_character(character_id)
        if row is None:
            row = CharacterBackstory(character_id=character_id, content=content)
            self.db.add(row)
        else:
            row.content = content

        await self.db.commit()
        await self.db.refresh(row)
        return row
