"""ORM models for a character's known spells, spell slots, and granted spells."""

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.models.enums import SpellLevelType
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


class CharacterSpellSlot(settings.Base):  # type: ignore
    """A character's spell slots for a given spell level (e.g. LEVEL_3 -> 4 total, 2 used)."""

    __tablename__ = "character_spell_slots"

    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)
    spell_level = Column(SpellLevelType, primary_key=True)
    total = Column(Integer, nullable=False, default=0)
    used = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("used >= 0", name="check_spell_slot_used_nonnegative"),
        CheckConstraint("used <= total", name="check_spell_slot_used_not_exceeding_total"),
    )

    def __repr__(self):
        return (
            f"<CharacterSpellSlot(character_id={self.character_id}, "
            f"level='{self.spell_level}', used={self.used}/{self.total})>"
        )


class CharacterGrantedSpell(settings.Base):  # type: ignore
    """
    A spell granted to a character by a feature/feat — deliberately separate
    from the limited "known spells" table ``character_spells`` and never
    competing for its budget. A character may hold the same spell from
    multiple grants; the unique constraint therefore keys on
    ``source_character_feature_id`` rather than the plain pair.
    """

    __tablename__ = "character_granted_spells"

    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    spell_id = Column(Integer, ForeignKey("spells.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_character_feature_id = Column(
        Integer,
        ForeignKey("character_features.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    character = relationship("Character", back_populates="granted_spells")
    spell = relationship("Spell")
    source_grant = relationship("CharacterFeature")

    def __repr__(self):
        return (
            f"<CharacterGrantedSpell(character_id={self.character_id}, spell_id={self.spell_id}, "
            f"source={self.source_character_feature_id})>"
        )
