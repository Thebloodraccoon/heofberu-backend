"""Item repository: base CRUD with in-use ownership guard."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_repository import BaseRepository
from app.models.character_item_model import CharacterItem
from app.models.item_model import Item


class ItemRepository(BaseRepository[Item]):
    """Item-specific repository built on :class:`BaseRepository`."""

    def __init__(self, db: AsyncSession):
        super().__init__(
            Item,
            db,
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    async def is_in_use(self, item_id: int) -> bool:
        """Return whether any character currently owns the item."""

        result = await self.db.execute(select(CharacterItem).where(CharacterItem.item_id == item_id))
        return result.scalar_one_or_none() is not None
