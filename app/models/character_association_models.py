from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.models.enums import AbilityScoreType, SpellLevelType
from app.settings import settings


class CharacterSkillProficiency(settings.Base):  # type: ignore
    """A character's proficiency (and optional expertise) in a given skill."""

    __tablename__ = "character_skill_proficiencies"

    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)
    skill_id = Column(Integer, ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True)
    is_expertise = Column(Boolean, nullable=False, default=False)

    skill = relationship("Skill")

    def __repr__(self):
        return f"<CharacterSkillProficiency(character_id={self.character_id}, skill_id={self.skill_id})>"


class CharacterSavingThrowProficiency(settings.Base):  # type: ignore
    """A character's proficiency in a given saving throw ability."""

    __tablename__ = "character_saving_throw_proficiencies"

    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)
    ability = Column(AbilityScoreType, primary_key=True)

    def __repr__(self):
        return f"<CharacterSavingThrowProficiency(character_id={self.character_id}, ability='{self.ability}')>"


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
