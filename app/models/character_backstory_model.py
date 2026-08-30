"""ORM model for a character's backstory (large free-text, stored uncached)."""

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from app.constants import BACKSTORY_MAX_LENGTH
from app.settings import settings


class CharacterBackstory(settings.Base):  # type: ignore
    """
    A character's backstory, isolated in its own table.

    The backstory can run several pages of text (up to
    ``BACKSTORY_MAX_LENGTH`` = 12000 characters), so it is deliberately kept
    OUT of the cached ``CharacterResponse`` — embedding a large blob in the
    Redis payload for every character read would bloat the cache for no
    benefit. It is served, uncached, through dedicated endpoints
    (``GET/PUT /characters/{id}/backstory``).
    """

    __tablename__ = "character_backstories"

    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)
    content = Column(Text, nullable=False, default="")

    __table_args__ = (
        CheckConstraint(
            f"char_length(content) <= {BACKSTORY_MAX_LENGTH}",
            name="check_character_backstory_max_length",
        ),
    )

    character = relationship("Character", back_populates="backstory")

    def __repr__(self):
        return f"<CharacterBackstory(character_id={self.character_id})>"
