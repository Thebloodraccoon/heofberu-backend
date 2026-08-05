"""ORM model for the reference table of playable races."""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.enums import RaceSizeType
from app.models.race_association_models import race_skills
from app.settings import settings


class Race(settings.Base):  # type: ignore
    """Reference table of playable races, shared across all characters."""

    __tablename__ = "races"

    id = Column(Integer, primary_key=True)

    name = Column(String(100), nullable=False, unique=True, index=True)
    size = Column(RaceSizeType, nullable=False)
    speed = Column(Integer, nullable=False, default=30)

    traits = Column(Text, nullable=False, default="")
    description = Column(Text, nullable=False, default="")

    is_homebrew = Column(Boolean, nullable=False, default=False)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    ability_bonuses = relationship(
        "RaceAbilityBonus",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    granted_skills = relationship(
        "Skill",
        secondary=race_skills,
    )
    characters = relationship("Character", back_populates="race")
    created_by = relationship("User")

    def __repr__(self):
        return f"<Race(id={self.id}, name='{self.name}')>"
