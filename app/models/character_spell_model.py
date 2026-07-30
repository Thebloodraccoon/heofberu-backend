from sqlalchemy import Boolean, Column, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.settings import settings


class CharacterSpell(settings.Base):  # type: ignore
    """
    Association between a character and a spell they know, with whether
    it is currently prepared (relevant for prepared-caster classes).
    """

    __tablename__ = "character_spells"

    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)
    spell_id = Column(Integer, ForeignKey("spells.id", ondelete="CASCADE"), primary_key=True)
    is_prepared = Column(Boolean, nullable=False, default=False)

    spell = relationship("Spell")

    def __repr__(self):
        return f"<CharacterSpell(character_id={self.character_id}, spell_id={self.spell_id})>"
