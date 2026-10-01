"""ORM model for a character's resolved choices within a feature grant."""

from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from app.settings import settings


class CharacterFeatureChoice(settings.Base):  # type: ignore
    """
    One selected option inside a grant's choice group.

    The unique ``(character_feature_id, choice_group_id, choice_option_id)``
    triple prevents double-picking the same option; whether the group is
    fully resolved (the chosen option count == ``pick_count``) is validated
    by the grant materializer service.
    """

    __tablename__ = "character_feature_choices"

    id = Column(Integer, primary_key=True)
    # No own index: the unique (character_feature_id, ...) already leads with this column.
    character_feature_id = Column(Integer, ForeignKey("character_features.id", ondelete="CASCADE"), nullable=False)
    choice_group_id = Column(
        Integer,
        ForeignKey("feature_choice_groups.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    choice_option_id = Column(
        Integer,
        ForeignKey("feature_choice_options.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "character_feature_id",
            "choice_group_id",
            "choice_option_id",
            name="uq_character_feature_choice_option",
        ),
    )

    character_feature = relationship("CharacterFeature", back_populates="choices")
    choice_group = relationship("FeatureChoiceGroup")
    choice_option = relationship("FeatureChoiceOption")

    def __repr__(self):
        return (
            f"<CharacterFeatureChoice(character_feature_id={self.character_feature_id}, "
            f"group_id={self.choice_group_id}, option_id={self.choice_option_id})>"
        )
