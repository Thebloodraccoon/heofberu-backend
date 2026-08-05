"""Item repository: base CRUD with in-use ownership guard."""

from sqlalchemy.orm import Session

from app.core.base_repository import BaseRepository
from app.models.character_item_model import CharacterItem
from app.models.item_model import Item


class ItemRepository(BaseRepository[Item]):
    """Item-specific repository built on :class:`BaseRepository`."""

    def __init__(self, db: Session):
        super().__init__(
            Item,
            db,
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    def is_in_use(self, item_id: int) -> bool:
        """Return whether any character currently owns the item."""
        return self.db.query(CharacterItem).filter(CharacterItem.item_id == item_id).first() is not None
