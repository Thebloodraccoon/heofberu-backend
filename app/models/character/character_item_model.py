"""ORM model for items owned by a character (stacks with equip/attunement state)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.character.character_model import Character
    from app.models.items.item_model import Item


class CharacterItem(Base):
    """
    An item owned by a character, with a quantity. A character may own
    multiple stacks of the same item (e.g. one spare), so this has its own
    surrogate key rather than a composite (character_id, item_id) primary key.

    ``is_equipped`` (worn/wielded) and ``is_attuned`` drive the computed AC and
    speeds: an item's armor and its speed/AC effects count only while equipped,
    and attuned too when the item ``requires_attunement``.
    """

    __tablename__ = "character_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), index=True)

    quantity: Mapped[int] = mapped_column(default=1)
    is_equipped: Mapped[bool] = mapped_column(default=False, server_default=false())
    is_attuned: Mapped[bool] = mapped_column(default=False, server_default=false())

    __table_args__ = (CheckConstraint("quantity >= 0", name="check_character_item_quantity_nonnegative"),)

    character: Mapped[Character] = relationship(back_populates="character_items")
    item: Mapped[Item] = relationship()

    def __repr__(self) -> str:
        return f"<CharacterItem(character_id={self.character_id}, item_id={self.item_id}, quantity={self.quantity})>"
