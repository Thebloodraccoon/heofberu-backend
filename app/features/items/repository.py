from sqlalchemy.orm import Session

from app.core.base_repository import BaseRepository
from app.models.character_item_model import CharacterItem
from app.models.item_model import Item


class ItemRepository(BaseRepository[Item]):
    def __init__(self, db: Session):
        super().__init__(Item, db, search_fields=["name"], unique_fields=["name"], check_in_use_on_delete=True,)

    def is_in_use(self, item_id: int) -> bool:
        """
        Check whether the item is currently owned by any character
        (character_items.item_id), which would block deletion at the DB
        level via ON DELETE RESTRICT.
        """
        return self.db.query(CharacterItem).filter(CharacterItem.item_id == item_id).first() is not None
