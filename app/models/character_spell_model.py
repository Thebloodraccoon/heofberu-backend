"""ORM model for the character <-> spell "known spells" association."""

from sqlalchemy import Column, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.settings import settings


class CharacterSpell(settings.Base):  # type: ignore
    """
    A spell the character has chosen/knows.

    Choosing a spell is capped by the character's spell slot totals: a
    character may know at most as many spells of a given ``Spell.level``
    as they have ``CharacterSpellSlot.total`` at that level — see
    ``CharacterSpellService.add_known_spell``. To swap a choice, remove
    the old one and add the new one; there's no separate "prepared"
    state — whatever is chosen here is what the character can cast,
    entirely at the GM's discretion for anything beyond that.
    """

    __tablename__ = "character_spells"

    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)
    spell_id = Column(Integer, ForeignKey("spells.id", ondelete="CASCADE"), primary_key=True)

    spell = relationship("Spell")

    def __repr__(self):
        return f"<CharacterSpell(character_id={self.character_id}, spell_id={self.spell_id})>"
