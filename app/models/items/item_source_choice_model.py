"""ORM models for source-owned starting-equipment choice groups."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import FeatureSourceType
from app.models.enums import FeatureSourceTypeType
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.items.item_model import Item


class SourceItemChoiceGroup(Base):
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

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[FeatureSourceType] = mapped_column(FeatureSourceTypeType, index=True)

    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    background_id: Mapped[int | None] = mapped_column(ForeignKey("backgrounds.id", ondelete="CASCADE"), index=True)

    pick_count: Mapped[int] = mapped_column(default=1)
    sort_order: Mapped[int] = mapped_column(default=0)

    __table_args__ = (CheckConstraint("pick_count >= 1", name="check_choice_group_pick_count_positive"),)

    options: Mapped[list[SourceItemChoiceOption]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SourceItemChoiceOption.sort_order",
    )

    def __repr__(self) -> str:
        return f"<SourceItemChoiceGroup(id={self.id}, source_type='{self.source_type}', pick_count={self.pick_count})>"


class SourceItemChoiceOption(Base):
    """
    One option inside a :class:`SourceItemChoiceGroup`.

    Each option points to an ``Item`` and optionally carries a ``quantity``
    (default 1). The player picks ``group.pick_count`` options from the
    group's options at character creation.
    """

    __tablename__ = "source_item_choice_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("source_item_choice_groups.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[int] = mapped_column(default=1)
    sort_order: Mapped[int] = mapped_column(default=0)

    group: Mapped[SourceItemChoiceGroup] = relationship(back_populates="options")
    item: Mapped[Item] = relationship()

    __table_args__ = (CheckConstraint("quantity >= 1", name="check_choice_option_quantity_positive"),)

    def __repr__(self) -> str:
        return f"<SourceItemChoiceOption(id={self.id}, group_id={self.group_id}, item_id={self.item_id})>"
