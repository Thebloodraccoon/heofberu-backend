from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.enums import AbilityScoreType
from app.settings import settings


class Skill(settings.Base):  # type: ignore
    """Reference table of skills (e.g. Perception, Stealth), shared across
    races, classes and characters."""

    __tablename__ = "skills"

    id = Column(Integer, primary_key=True)

    key = Column(String(50), nullable=False, unique=True, index=True)  # e.g. "PERCEPTION"
    name = Column(String(100), nullable=False)  # display name, e.g. "Perception"
    ability = Column(AbilityScoreType, nullable=False)  # governing ability score
    description = Column(Text, nullable=False, default="")

    def __repr__(self):
        return f"<Skill(id={self.id}, key='{self.key}')>"
