"""Repository for the item stacks owned by a character (``character_items``)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models.character_item_model import CharacterItem


class CharacterItemRepository(BaseRepository[CharacterItem]):
    """
    Repository for the items owned by a character (``character_items``).
    Each row is an independent stack, so the same item may be owned
    several times. Every read eager-loads the referenced ``Item``.
    """

    def __init__(self, db: AsyncSession):
        """Create the item-stack repository."""

        super().__init__(CharacterItem, db)

    def _stack_with_item(self, statement):
        """Return the query with the ``Item`` eager-loaded."""

        return statement.options(selectinload(CharacterItem.item))

    async def get_character_items(self, character_id: int) -> list[CharacterItem]:
        """Get every item stack owned by a character."""

        result = await self.db.execute(
            self._stack_with_item(select(CharacterItem).where(CharacterItem.character_id == character_id))
        )
        return list(result.scalars().unique().all())

    async def get_character_item_by_id(self, character_id: int, character_item_id: int) -> CharacterItem | None:
        """Fetch a single item stack by its own id, scoped to the character."""

        result = await self.db.execute(
            self._stack_with_item(
                select(CharacterItem).where(
                    CharacterItem.id == character_item_id,
                    CharacterItem.character_id == character_id,
                )
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

        return await self._fetch_with_item(stack.id)

    async def update_character_item(self, stack: CharacterItem, fields: dict) -> CharacterItem:
        """Apply a PATCH field dict onto an item stack and commit."""

        for field, value in fields.items():
            setattr(stack, field, value)

        await self.db.commit()

        return await self._fetch_with_item(stack.id)

    async def remove_character_item(self, stack: CharacterItem) -> bool:
        """Remove an item stack from a character."""

        await self.db.delete(stack)
        await self.db.commit()
        return True

    async def _fetch_with_item(self, stack_id: int) -> CharacterItem:
        """Re-fetch one stack with its item eager-loaded (post-commit)."""

        result = await self.db.execute(self._stack_with_item(select(CharacterItem).where(CharacterItem.id == stack_id)))
        return result.scalar_one()