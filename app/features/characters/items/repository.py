"""Character item repository: character-item stack CRUD."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.repository import BaseRepository
from app.models.character_item_model import CharacterItem


class CharacterItemRepository(BaseRepository[CharacterItem]):
    """
    Repository for the items owned by a character (``character_items``).

    Each row is an independent stack, so the same item may be owned
    several times (e.g. an equipped sword and a spare).
    """

    def __init__(self, db: AsyncSession):
        super().__init__(CharacterItem, db)

    async def get_character_items(self, character_id: int) -> list[CharacterItem]:
        """Get every item stack owned by a character."""

        result = await self.db.execute(select(CharacterItem).where(CharacterItem.character_id == character_id))
        return list(result.scalars().unique().all())

    async def get_character_item_by_id(self, character_id: int, character_item_id: int) -> CharacterItem | None:
        """Fetch a single item stack by its own id, scoped to the character."""

        result = await self.db.execute(
            select(CharacterItem).where(
                CharacterItem.id == character_item_id,
                CharacterItem.character_id == character_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_character_item(
        self,
        character_id: int,
        item_id: int,
        quantity: int,
        is_equipped: bool,
        is_attuned: bool,
        notes: str,
    ) -> CharacterItem:
        """Add an item stack to a character."""

        stack = CharacterItem(
            character_id=character_id,
            item_id=item_id,
            quantity=quantity,
            is_equipped=is_equipped,
            is_attuned=is_attuned,
            notes=notes,
        )

        self.db.add(stack)
        await self.db.commit()
        await self.db.refresh(stack)

        return stack

    async def remove_character_item(self, stack: CharacterItem) -> bool:
        """Remove an item stack from a character."""

        await self.db.delete(stack)
        await self.db.commit()
        return True
