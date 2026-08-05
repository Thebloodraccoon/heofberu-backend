"""ORM model for items owned by a character (stacks with equip/attunement state)."""

from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from app.settings import settings


class CharacterItem(settings.Base):  # type: ignore
    """
    An item owned by a character, with quantity and equip/attunement
    state. A character may own multiple stacks of the same item (e.g. one
    equipped sword, one spare), so this has its own surrogate key rather
    than a composite (character_id, item_id) primary key.
    """

    __tablename__ = "character_items"

    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False, index=True)

    quantity = Column(Integer, nullable=False, default=1)
    is_equipped = Column(Boolean, nullable=False, default=False)
    is_attuned = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, nullable=False, default="")

    __table_args__ = (CheckConstraint("quantity >= 0", name="check_character_item_quantity_nonnegative"),)

    character = relationship("Character", back_populates="character_items")
    item = relationship("Item")

    def __repr__(self):
        return f"<CharacterItem(character_id={self.character_id}, item_id={self.item_id}, quantity={self.quantity})>"
