"""ORM models for source-owned starting-equipment choice groups."""

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.models.enums import FeatureSourceTypeType
from app.settings import settings


class SourceItemChoiceGroup(settings.Base):  # type: ignore
    """
    A choice group within a class's or background's starting equipment.

    Each group represents a "pick N from M options" decision the player
    makes at character creation. For example, a Bard class might define:
      - Group 1 (pick 1): rapier OR longsword
      - Group 2 (pick 1): diplomat's pack OR entertainer's pack

    ``source_type`` + the relevant FK indicate where the group belongs.
    ``pick_count`` is how many options from this group are granted (usually 1).
    ``sort_order`` controls display order.
    """

    __tablename__ = "source_item_choice_groups"

    id = Column(Integer, primary_key=True)
    source_type = Column(FeatureSourceTypeType, nullable=False, index=True)

    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=True, index=True)
    background_id = Column(Integer, ForeignKey("backgrounds.id", ondelete="CASCADE"), nullable=True, index=True)

    pick_count = Column(Integer, nullable=False, default=1)
    sort_order = Column(Integer, nullable=False, default=0)

    __table_args__ = (CheckConstraint("pick_count >= 1", name="check_choice_group_pick_count_positive"),)

    options = relationship(
        "SourceItemChoiceOption",
        back_populates="group",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SourceItemChoiceOption.sort_order",
    )

    def __repr__(self):
        return f"<SourceItemChoiceGroup(id={self.id}, source_type='{self.source_type}', pick_count={self.pick_count})>"


class SourceItemChoiceOption(settings.Base):  # type: ignore
    """
    One option inside a :class:`SourceItemChoiceGroup`.

    Each option points to an ``Item`` and optionally carries a ``quantity``
    (default 1). The player picks ``group.pick_count`` options from the
    group's options at character creation.
    """

    __tablename__ = "source_item_choice_options"

    id = Column(Integer, primary_key=True)
    group_id = Column(
        Integer,
        ForeignKey("source_item_choice_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_id = Column(Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=1)
    sort_order = Column(Integer, nullable=False, default=0)

    group = relationship("SourceItemChoiceGroup", back_populates="options")
    item = relationship("Item")

    __table_args__ = (CheckConstraint("quantity >= 1", name="check_choice_option_quantity_positive"),)

    def __repr__(self):
        return f"<SourceItemChoiceOption(id={self.id}, group_id={self.group_id}, item_id={self.item_id})>"
