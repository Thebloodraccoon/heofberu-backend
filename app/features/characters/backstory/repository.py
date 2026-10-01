"""Character backstory repository: single-row get/upsert (uncached)."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.repository import BaseRepository
from app.models.character.character_backstory_model import CharacterBackstory


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
        """Create the backstory row or replace its content in one ``INSERT ... ON CONFLICT DO UPDATE``, and commit."""

        statement = pg_insert(CharacterBackstory).values(character_id=character_id, content=content)
        statement = statement.on_conflict_do_update(
            index_elements=[CharacterBackstory.character_id], set_={"content": statement.excluded.content}
        ).returning(CharacterBackstory)

        row = await self.db.scalar(statement, execution_options={"populate_existing": True})
        await self.commit_or_flush()
        return row
