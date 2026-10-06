"""ORM model for a character's resolved choices within a feature grant."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.character.character_feature_model import CharacterFeature
    from app.models.features.feature_engine_models import FeatureChoiceGroup, FeatureChoiceOption


class CharacterFeatureChoice(Base):
    """
    One selected option inside a grant's choice group.

    The unique ``(character_feature_id, choice_group_id, choice_option_id)``
    triple prevents double-picking the same option; whether the group is
    fully resolved (the chosen option count == ``pick_count``) is validated
    by the grant materializer service.
    """

    __tablename__ = "character_feature_choices"

    id: Mapped[int] = mapped_column(primary_key=True)
    # No own index: the unique (character_feature_id, ...) already leads with this column.
    character_feature_id: Mapped[int] = mapped_column(ForeignKey("character_features.id", ondelete="CASCADE"))
    choice_group_id: Mapped[int] = mapped_column(
        ForeignKey("feature_choice_groups.id", ondelete="RESTRICT"), index=True
    )
    choice_option_id: Mapped[int] = mapped_column(
        ForeignKey("feature_choice_options.id", ondelete="RESTRICT"), index=True
    )

    __table_args__ = (
        UniqueConstraint(
            "character_feature_id",
            "choice_group_id",
            "choice_option_id",
            name="uq_character_feature_choice_option",
        ),
    )

    character_feature: Mapped[CharacterFeature] = relationship(back_populates="choices")
    choice_group: Mapped[FeatureChoiceGroup] = relationship()
    choice_option: Mapped[FeatureChoiceOption] = relationship()

    def __repr__(self) -> str:
        return (
            f"<CharacterFeatureChoice(character_feature_id={self.character_feature_id}, "
            f"group_id={self.choice_group_id}, option_id={self.choice_option_id})>"
        )
