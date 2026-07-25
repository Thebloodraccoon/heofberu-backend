from sqlalchemy import Boolean, Column, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.settings import settings


class Race(settings.Base):  # type: ignore
    """Reference table of playable races, shared across all characters."""

    __tablename__ = "races"

    id = Column(Integer, primary_key=True)

    name = Column(String(100), nullable=False, unique=True, index=True)
    size = Column(String(20), nullable=False, default="Средний")
    speed = Column(Integer, nullable=False, default=30)

    # Structured data, mirrors the original SQLite JSON-in-TEXT fields
    ability_bonuses = Column(JSONB, nullable=False, default=dict)  # e.g. {"STR": 2, "CON": 1}
    granted_skills = Column(JSONB, nullable=False, default=list)  # e.g. ["PERCEPTION", "STEALTH"]

    traits = Column(Text, nullable=False, default="")
    description = Column(Text, nullable=False, default="")

    is_homebrew = Column(Boolean, nullable=False, default=False)

    characters = relationship("Character", back_populates="race")

    def __repr__(self):
        return f"<Race(id={self.id}, name='{self.name}')>"
