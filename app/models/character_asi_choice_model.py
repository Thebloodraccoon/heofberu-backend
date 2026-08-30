"""ORM models for a character's resolved Ability Score Improvement choices."""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.enums import AbilityScoreType, ASILevelChoiceType
from app.settings import settings


class CharacterASIChoice(settings.Base):  # type: ignore
    """
    One resolved Ability Score Improvement opportunity for a character.

    A row is created either by a level-up through an ASI class level
    (4/8/12/16/19 by default, ``class_level`` set) recording which of the
    two 5e options was taken:

      - ASI: ``increases`` holds the chosen increments as child
        ``CharacterASIChoiceIncrease`` rows (e.g. STR +2).
      - FEAT: ``feat_id`` (+ optional ``ability_score_increase_id``) points
        at the chosen feat, which is also granted as a
        ``character_feats`` row with ``source_type`` ``"ASI"``.

    ...or by a GM adjustment from the GM panel (``class_level`` NULL):
    a free-form ±increase bound to no class level. PostgreSQL treats
    NULLs as distinct in the unique constraint, so a character may hold
    any number of GM adjustments.

    The unique ``(character_id, class_level)`` pair guarantees each ASI
    level is resolved at most once. This table is both the audit trail
    behind ``CharacterProgressionService``/the GM panel AND the counted
    source of ASI points: base ability columns on ``Character`` stay at
    their originally entered values, and the effective totals are
    computed as base + race/subrace/feat bonuses + every increase row of
    choices with ``applied_to_base == False``.

    Legacy flag: rows created before the log-based rework had their ASI
    increments added straight onto the base columns (and their JSONB
    payload expanded here by migration); those rows carry
    ``applied_to_base = True`` and are deliberately NOT counted by the
    calculator, otherwise their points would apply twice.
    """

    __tablename__ = "character_asi_choices"

    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    class_level = Column(Integer, nullable=True)
    choice_type = Column(ASILevelChoiceType, nullable=False)

    feat_id = Column(Integer, ForeignKey("feats.id", ondelete="RESTRICT"), nullable=True, index=True)
    ability_score_increase_id = Column(Integer, ForeignKey("feat_ability_score_increases.id", ondelete="SET NULL"))

    # True for pre-rework rows whose points were already folded into the
    # base columns — excluded from the calculator to avoid double counting.
    # All new rows are written with False (the default): their increases
    # live ONLY in the child rows below.
    applied_to_base = Column(Boolean, nullable=False, default=False, server_default="false")

    __table_args__ = (UniqueConstraint("character_id", "class_level", name="uq_character_asi_choice_level"),)

    character = relationship("Character", back_populates="asi_choices")
    feat = relationship("Feat")

    # The counted increments of this choice (empty for FEAT-type rows,
    # whose stat effect flows through the granted ``character_feats`` row).
    increases = relationship(
        "CharacterASIChoiceIncrease",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CharacterASIChoiceIncrease.id",
    )

    def __repr__(self):
        return (
            f"<CharacterASIChoice(character_id={self.character_id}, "
            f"class_level={self.class_level}, choice_type='{self.choice_type}')>"
        )


class CharacterASIChoiceIncrease(settings.Base):  # type: ignore
    """
    A single counted increment of a ``CharacterASIChoice``, e.g.
    {choice: level-4 ASI, ability: STR, amount: 2}. Mirrors the
    ``FeatAbilityScoreIncrease`` child-row pattern: typed ability +
    amount columns instead of an untyped JSONB blob, queryable by the
    ability-score calculator with a plain join.
    """

    __tablename__ = "character_asi_choice_increases"

    id = Column(Integer, primary_key=True)
    character_asi_choice_id = Column(
        Integer,
        ForeignKey("character_asi_choices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    ability = Column(AbilityScoreType, nullable=False)
    amount = Column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("character_asi_choice_id", "ability", name="uq_character_asi_inc_ability"),)

    choice = relationship("CharacterASIChoice", back_populates="increases")

    def __repr__(self):
        return (
            f"<CharacterASIChoiceIncrease(choice_id={self.character_asi_choice_id}, "
            f"ability='{self.ability}', amount={self.amount})>"
        )
