"""ORM models for a character's resolved Ability Score Improvement choices."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import AbilityScore, ASILevelChoice
from app.models.enums import AbilityScoreType, ASILevelChoiceType
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.character.character_model import Character


class CharacterASIChoice(Base):
    """
    One resolved Ability Score Improvement opportunity for a character.

    A row is created either by a level-up through an ASI class level
    (4/8/12/16/19 by default, ``class_level`` set) recording which of the
    two 5e options was taken:

      - ASI: ``increases`` holds the chosen increments as child
        ``CharacterASIChoiceIncrease`` rows (e.g. STR +2).
      - FEAT: ``feat_id`` (+ optional ``ability_score_increase_id``) points
        at the chosen feat — a ``features`` row with ``source_type``
        ``"FEAT"`` — which is also granted as a ``character_features`` row
        with ``grant_source`` ``"ASI"``.

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

    id: Mapped[int] = mapped_column(primary_key=True)
    # No own index: ``uq_character_asi_choice_level`` (character_id, class_level) already leads with it.
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    class_level: Mapped[int | None] = mapped_column()
    choice_type: Mapped[ASILevelChoice] = mapped_column(ASILevelChoiceType)

    feat_id: Mapped[int | None] = mapped_column(ForeignKey("features.id", ondelete="RESTRICT"), index=True)
    ability_score_increase_id: Mapped[int | None] = mapped_column(
        ForeignKey("feature_ability_score_effects.id", ondelete="SET NULL"), index=True
    )

    # True for pre-rework rows whose points were already folded into the
    # base columns — excluded from the calculator to avoid double counting.
    # All new rows are written with False (the default): their increases
    # live ONLY in the child rows below.
    applied_to_base: Mapped[bool] = mapped_column(default=False, server_default="false")

    __table_args__ = (
        UniqueConstraint("character_id", "class_level", name="uq_character_asi_choice_level"),
        CheckConstraint("choice_type <> 'FEAT' OR feat_id IS NOT NULL", name="ck_character_asi_choice_feat_has_feat"),
        # Upper bound = CHARACTER_MAX_LEVEL.
        CheckConstraint("class_level IS NULL OR class_level BETWEEN 1 AND 20", name="ck_character_asi_choice_level"),
    )

    character: Mapped[Character] = relationship(back_populates="asi_choices")

    # The counted increments of this choice (empty for FEAT-type rows,
    # whose stat effect flows through the granted feat's effect engine).
    increases: Mapped[list[CharacterASIChoiceIncrease]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CharacterASIChoiceIncrease.id",
    )

    def __repr__(self) -> str:
        return (
            f"<CharacterASIChoice(character_id={self.character_id}, "
            f"class_level={self.class_level}, choice_type='{self.choice_type}')>"
        )


class CharacterASIChoiceIncrease(Base):
    """
    A single counted increment of a ``CharacterASIChoice``, e.g.
    {choice: level-4 ASI, ability: STR, amount: 2}. Mirrors the
    ``FeatureAbilityScoreEffect`` child-row pattern: typed ability +
    amount columns instead of an untyped JSONB blob, queryable by the
    ability-score calculator with a plain join.
    """

    __tablename__ = "character_asi_choice_increases"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_asi_choice_id: Mapped[int] = mapped_column(
        ForeignKey("character_asi_choices.id", ondelete="CASCADE"), index=True
    )

    ability: Mapped[AbilityScore] = mapped_column(AbilityScoreType)
    amount: Mapped[int] = mapped_column()

    __table_args__ = (
        UniqueConstraint("character_asi_choice_id", "ability", name="uq_character_asi_inc_ability"),
        # Upper bound = MAX_ABILITY_SCORE_CAP (the GM-panel schema limit).
        CheckConstraint("amount BETWEEN -30 AND 30", name="ck_character_asi_increase_amount"),
    )

    choice: Mapped[CharacterASIChoice] = relationship(back_populates="increases")

    def __repr__(self) -> str:
        return (
            f"<CharacterASIChoiceIncrease(choice_id={self.character_asi_choice_id}, "
            f"ability='{self.ability}', amount={self.amount})>"
        )
