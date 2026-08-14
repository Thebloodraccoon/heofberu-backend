"""ORM model for source-owned starting equipment (classes, backgrounds)."""

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.models.enums import FeatureSourceTypeType
from app.settings import settings


class SourceItem(settings.Base):  # type: ignore
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

    id = Column(Integer, primary_key=True)
    source_type = Column(FeatureSourceTypeType, nullable=False, index=True)

    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=True, index=True)
    background_id = Column(Integer, ForeignKey("backgrounds.id", ondelete="CASCADE"), nullable=True, index=True)

    item_id = Column(Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=1)

    __table_args__ = (CheckConstraint("quantity >= 0", name="check_source_item_quantity_nonnegative"),)

    item = relationship("Item")

    def __repr__(self):
        return f"<SourceItem(id={self.id}, source_type='{self.source_type}', item_id={self.item_id}, quantity={self.quantity})>"
