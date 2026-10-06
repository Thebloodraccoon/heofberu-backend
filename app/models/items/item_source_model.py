"""ORM model for source-owned starting equipment (classes, backgrounds)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import FeatureSourceType
from app.models.enums import FeatureSourceTypeType
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.items.item_model import Item


class SourceItem(Base):
    """
    A starting-equipment entry owned by a class or background.

    Mirrors the polymorphic ``features`` table: one row per (source, item)
    with a ``source_type`` pinning which FK applies. Only CLASS/BACKGROUND
    are meaningful for starting equipment; the other ``FeatureSourceType``
    values are rejected at the schema layer.

    Deleting a source row cascades its entries away (``ON DELETE CASCADE``);
    an item referenced here cannot be deleted until the link is removed
    (``ON DELETE RESTRICT`` on ``item_id``).
    """

    __tablename__ = "source_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[FeatureSourceType] = mapped_column(FeatureSourceTypeType, index=True)

    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    background_id: Mapped[int | None] = mapped_column(ForeignKey("backgrounds.id", ondelete="CASCADE"), index=True)

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[int] = mapped_column(default=1)

    __table_args__ = (CheckConstraint("quantity >= 0", name="check_source_item_quantity_nonnegative"),)

    item: Mapped[Item] = relationship()

    def __repr__(self) -> str:
        return f"<SourceItem(id={self.id}, source_type='{self.source_type}', item_id={self.item_id}, quantity={self.quantity})>"
