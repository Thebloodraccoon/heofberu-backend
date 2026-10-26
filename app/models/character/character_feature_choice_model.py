"""ORM model for a character's resolved choices within a feature grant."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import AbilityScore
from app.models.enums import AbilityScoreType
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.character.character_feature_model import CharacterFeature
    from app.models.features.feature_engine_models import FeatureChoiceGroup, FeatureChoiceOption


class CharacterFeatureChoice(Base):
    """
    One selected option inside a grant's choice group.

    ``picked_skill_id`` is the skill the player named for an option with an
    open ("any skill") skill effect, ``picked_spell_id`` the spell named for
    an option with an open ("any spell") spell effect, ``picked_ability`` the
    ability named for an open ("any ability" / "any saving throw") effect,
    ``picked_item_id`` the tool named for an open ("any tool") tool effect;
    all NULL for every other option (an option is open in one way at most —
    a group carries one effect type). Such an option may be picked several
    times in one group with different skills/spells/abilities ("any two
    skills" = one open option, ``pick_count=2``).

    Five partial unique indexes prevent double-picking: the same option
    twice (nothing named), or the same option with the same skill / spell / ability / tool.
    Whether the group is fully resolved (the chosen count == ``pick_count``)
    is validated by the grant service.
    """

    __tablename__ = "character_feature_choices"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Own index: the unique indexes below are partial, so ``WHERE character_feature_id IN (...)`` can't use them.
    character_feature_id: Mapped[int] = mapped_column(
        ForeignKey("character_features.id", ondelete="CASCADE"), index=True
    )
    choice_group_id: Mapped[int] = mapped_column(
        ForeignKey("feature_choice_groups.id", ondelete="RESTRICT"), index=True
    )
    choice_option_id: Mapped[int] = mapped_column(
        ForeignKey("feature_choice_options.id", ondelete="RESTRICT"), index=True
    )
    picked_skill_id: Mapped[int | None] = mapped_column(ForeignKey("skills.id", ondelete="RESTRICT"), index=True)
    picked_spell_id: Mapped[int | None] = mapped_column(ForeignKey("spells.id", ondelete="RESTRICT"), index=True)
    picked_ability: Mapped[AbilityScore | None] = mapped_column(AbilityScoreType)
    picked_item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), index=True)

    __table_args__ = (
        Index(
            "uq_character_feature_choice_option",
            "character_feature_id",
            "choice_group_id",
            "choice_option_id",
            unique=True,
            postgresql_where=text(
                "picked_skill_id IS NULL AND picked_spell_id IS NULL AND picked_ability IS NULL "
                "AND picked_item_id IS NULL"
            ),
        ),
        Index(
            "uq_character_feature_choice_option_ability",
            "character_feature_id",
            "choice_group_id",
            "choice_option_id",
            "picked_ability",
            unique=True,
            postgresql_where=text("picked_ability IS NOT NULL"),
        ),
        Index(
            "uq_character_feature_choice_option_skill",
            "character_feature_id",
            "choice_group_id",
            "choice_option_id",
            "picked_skill_id",
            unique=True,
            postgresql_where=text("picked_skill_id IS NOT NULL"),
        ),
        Index(
            "uq_character_feature_choice_option_spell",
            "character_feature_id",
            "choice_group_id",
            "choice_option_id",
            "picked_spell_id",
            unique=True,
            postgresql_where=text("picked_spell_id IS NOT NULL"),
        ),
        Index(
            "uq_character_feature_choice_option_item",
            "character_feature_id",
            "choice_group_id",
            "choice_option_id",
            "picked_item_id",
            unique=True,
            postgresql_where=text("picked_item_id IS NOT NULL"),
        ),
    )

    character_feature: Mapped[CharacterFeature] = relationship(back_populates="choices")
    choice_group: Mapped[FeatureChoiceGroup] = relationship()
    choice_option: Mapped[FeatureChoiceOption] = relationship()

    def __repr__(self) -> str:
        return (
            f"<CharacterFeatureChoice(character_feature_id={self.character_feature_id}, "
            f"group_id={self.choice_group_id}, option_id={self.choice_option_id}, "
            f"skill_id={self.picked_skill_id}, spell_id={self.picked_spell_id}, ability={self.picked_ability}, "
            f"item_id={self.picked_item_id})>"
        )
