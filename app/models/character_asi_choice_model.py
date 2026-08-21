"""ORM model for a character's resolved Ability Score Improvement level choices."""

from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.models.enums import ASILevelChoiceType
from app.settings import settings


class CharacterASIChoice(settings.Base):  # type: ignore
    """
    One resolved Ability Score Improvement opportunity for a character.

    A row is created either by a level-up through an ASI class level
    (4/8/12/16/19 by default, ``class_level`` set) recording which of the
    two 5e options was taken:

      - ASI: ``increases`` holds ``[{"ability": "STR", "amount": 2}]`` and
        the base ability columns on ``Character`` are bumped directly.
      - FEAT: ``feat_id`` (+ optional ``ability_score_increase_id``) points
        at the chosen feat, which is also granted as a
        ``character_feats`` row with ``source_type`` ``"ASI"``.

    ...or by a GM adjustment from the GM panel (``class_level`` NULL):
    a free-form ±increase applied straight to the base columns, bound to
    no class level. PostgreSQL treats NULLs as distinct in the unique
    constraint, so a character may hold any number of GM adjustments.

    The unique ``(character_id, class_level)`` pair guarantees each ASI
    level is resolved at most once. This table is the audit trail behind
    ``CharacterProgressionService`` and the GM panel; the base columns /
    feat grant rows are the source of truth the ability-score cache is
    computed from.
    """

    __tablename__ = "character_asi_choices"

    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    class_level = Column(Integer, nullable=True)
    choice_type = Column(ASILevelChoiceType, nullable=False)

    feat_id = Column(Integer, ForeignKey("feats.id", ondelete="RESTRICT"), nullable=True, index=True)
    ability_score_increase_id = Column(Integer, ForeignKey("feat_ability_score_increases.id", ondelete="SET NULL"))

    # Only set for choice_type == ASI: [{"ability": "STR", "amount": 2}].
    increases = Column(JSONB, nullable=True)

    __table_args__ = (UniqueConstraint("character_id", "class_level", name="uq_character_asi_choice_level"),)

    character = relationship("Character", back_populates="asi_choices")
    feat = relationship("Feat")

    def __repr__(self):
        return (
            f"<CharacterASIChoice(character_id={self.character_id}, "
            f"class_level={self.class_level}, choice_type='{self.choice_type}')>"
        )
