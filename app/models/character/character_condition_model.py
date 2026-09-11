"""ORM model for active conditions/status effects on a character."""

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from app.models.enums import ConditionTypeType
from app.settings import settings


class CharacterCondition(settings.Base):  # type: ignore
    """
    An active condition/status effect currently affecting a character
    (e.g. Poisoned, Prone, Exhaustion level 2). `exhaustion_level` is only
    meaningful when condition is EXHAUSTION (5e tracks exhaustion in levels
    1-6 rather than as a boolean).
    """

    __tablename__ = "character_conditions"

    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)
    condition = Column(ConditionTypeType, primary_key=True)

    exhaustion_level = Column(Integer, nullable=True)
    source = Column(Text, nullable=False, default="")  # e.g. "Poisoned by Giant Spider bite"

    __table_args__ = (
        CheckConstraint(
            "exhaustion_level IS NULL OR (exhaustion_level >= 1 AND exhaustion_level <= 6)",
            name="check_character_condition_exhaustion_level_range",
        ),
    )

    character = relationship("Character", back_populates="conditions")

    def __repr__(self):
        return f"<CharacterCondition(character_id={self.character_id}, condition='{self.condition}')>"
