from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, Integer, UniqueConstraint
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


class CharacterFeat(settings.Base):  # type: ignore
    """
    A feat granted to a character. Uses a surrogate key rather than a
    composite (character_id, feat_id) PK because some feats can be taken
    more than once (e.g. Elemental Adept for different damage types).

    `ability_score_increase_id` records which of the feat's ASI choices
    (see FeatAbilityScoreIncrease) the player selected, if any; NULL if
    the feat grants no ability score increase or none was applicable.
    """

    __tablename__ = "character_feats"

    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    feat_id = Column(Integer, ForeignKey("feats.id", ondelete="RESTRICT"), nullable=False, index=True)
    ability_score_increase_id = Column(
        Integer,
        ForeignKey("feat_ability_score_increases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    __table_args__ = (UniqueConstraint("character_id", "feat_id", name="uq_character_feat"),)

    character = relationship("Character", back_populates="character_feats")
    feat = relationship("Feat")
    ability_score_increase = relationship("FeatAbilityScoreIncrease")

    def __repr__(self):
        return f"<CharacterFeat(character_id={self.character_id}, feat_id={self.feat_id})>"
