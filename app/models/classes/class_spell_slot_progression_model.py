"""ORM model for the class spell-slot progression reference table."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import SpellLevel
from app.models.enums import SpellLevelType
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.classes.class_model import Class


class ClassSpellSlotProgression(Base):
    """
    Reference table describing how many spell slots of a given spell
    level a class grants at a given character level, e.g.
    (class=Wizard, class_level=5, spell_level=LEVEL_3) -> slots=2.
    Drives slot totals when applying a level-up, rather than hardcoding
    progression tables in application code.
    """

    __tablename__ = "class_spell_slot_progressions"

    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True)
    class_level: Mapped[int] = mapped_column(primary_key=True)
    spell_level: Mapped[SpellLevel] = mapped_column(SpellLevelType, primary_key=True)

    slots: Mapped[int] = mapped_column(default=0)

    __table_args__ = (
        CheckConstraint("class_level >= 1 AND class_level <= 20", name="check_progression_class_level_range"),
        CheckConstraint("slots >= 0", name="check_progression_slots_nonnegative"),
    )

    character_class: Mapped[Class] = relationship(viewonly=True)

    def __repr__(self) -> str:
        return (
            f"<ClassSpellSlotProgression(class_id={self.class_id}, "
            f"class_level={self.class_level}, spell_level='{self.spell_level}', slots={self.slots})>"
        )
