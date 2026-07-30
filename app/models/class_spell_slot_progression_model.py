from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.models.enums import SpellLevelType
from app.settings import settings


class ClassSpellSlotProgression(settings.Base):  # type: ignore
    """
    Reference table describing how many spell slots of a given spell
    level a class grants at a given character level, e.g.
    (class=Wizard, class_level=5, spell_level=LEVEL_3) -> slots=2.
    Drives slot totals when applying a level-up, rather than hardcoding
    progression tables in application code.
    """

    __tablename__ = "class_spell_slot_progressions"

    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True)
    class_level = Column(Integer, primary_key=True)
    spell_level = Column(SpellLevelType, primary_key=True)

    slots = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("class_level >= 1 AND class_level <= 20", name="check_progression_class_level_range"),
        CheckConstraint("slots >= 0", name="check_progression_slots_nonnegative"),
    )

    character_class = relationship("Class")

    def __repr__(self):
        return (
            f"<ClassSpellSlotProgression(class_id={self.class_id}, "
            f"class_level={self.class_level}, spell_level='{self.spell_level}', slots={self.slots})>"
        )
