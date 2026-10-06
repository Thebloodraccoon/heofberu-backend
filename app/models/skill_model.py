"""ORM model for the reference table of skills."""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import AbilityScore
from app.models.enums import AbilityScoreType
from app.settings.base import Base


class Skill(Base):
    """
    Reference table of skills (e.g. Perception, Stealth), shared across
    races, classes and characters.
    """

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)  # e.g. "Perception"
    ability: Mapped[AbilityScore] = mapped_column(AbilityScoreType)  # governing ability score
    description: Mapped[str] = mapped_column(Text, default="")

    def __repr__(self) -> str:
        return f"<Skill(id={self.id}, name='{self.name}')>"
