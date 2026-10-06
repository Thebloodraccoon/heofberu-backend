"""ORM models for a character's known spells, spell slots, and granted spells."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import SpellLevel
from app.models.enums import SpellLevelType
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.character.character_model import Character
    from app.models.spells.spell_model import Spell


class CharacterSpell(Base):
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

    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)
    spell_id: Mapped[int] = mapped_column(ForeignKey("spells.id", ondelete="CASCADE"), primary_key=True, index=True)

    spell: Mapped[Spell] = relationship()

    def __repr__(self) -> str:
        return f"<CharacterSpell(character_id={self.character_id}, spell_id={self.spell_id})>"


class CharacterSpellSlot(Base):
    """A character's spell slots for a given spell level (e.g. LEVEL_3 -> 4 total, 2 used)."""

    __tablename__ = "character_spell_slots"

    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)
    spell_level: Mapped[SpellLevel] = mapped_column(SpellLevelType, primary_key=True)
    total: Mapped[int] = mapped_column(default=0)
    used: Mapped[int] = mapped_column(default=0)

    __table_args__ = (
        CheckConstraint("used >= 0", name="check_spell_slot_used_nonnegative"),
        CheckConstraint("used <= total", name="check_spell_slot_used_not_exceeding_total"),
    )

    def __repr__(self) -> str:
        return (
            f"<CharacterSpellSlot(character_id={self.character_id}, "
            f"level='{self.spell_level}', used={self.used}/{self.total})>"
        )


class CharacterGrantedSpell(Base):
    """
    A spell the GM granted to a character directly (a homebrew boon) —
    separate from the limited "known spells" table ``character_spells`` and
    never competing for its budget. Spells from feature/feat grants are not
    stored here: they are computed on read from the grant
    (``app.features.characters.grants.effects``). At most one row per
    (character, spell), so the GM panel addresses a grant by ``spell_id``.
    """

    __tablename__ = "character_granted_spells"
    __table_args__ = (UniqueConstraint("character_id", "spell_id", name="uq_character_granted_spell"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    spell_id: Mapped[int] = mapped_column(ForeignKey("spells.id", ondelete="RESTRICT"), index=True)

    character: Mapped[Character] = relationship(back_populates="granted_spells")
    spell: Mapped[Spell] = relationship()

    def __repr__(self) -> str:
        return f"<CharacterGrantedSpell(character_id={self.character_id}, spell_id={self.spell_id})>"
