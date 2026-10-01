"""ORM model for active conditions/status effects on a character."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import ConditionType
from app.models.enums import ConditionTypeType
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.character.character_model import Character


class CharacterCondition(Base):
    """
    An active condition/status effect currently affecting a character
    (e.g. Poisoned, Prone, Exhaustion level 2). `exhaustion_level` is only
    meaningful when condition is EXHAUSTION (5e tracks exhaustion in levels
    1-6 rather than as a boolean).
    """

    __tablename__ = "character_conditions"

    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)
    condition: Mapped[ConditionType] = mapped_column(ConditionTypeType, primary_key=True)

    exhaustion_level: Mapped[int | None] = mapped_column()
    source: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        CheckConstraint(
            "exhaustion_level IS NULL OR (exhaustion_level >= 1 AND exhaustion_level <= 6)",
            name="check_character_condition_exhaustion_level_range",
        ),
    )

    character: Mapped[Character] = relationship(back_populates="conditions")

    def __repr__(self) -> str:
        return f"<CharacterCondition(character_id={self.character_id}, condition='{self.condition}')>"
