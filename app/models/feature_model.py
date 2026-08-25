"""ORM models for the reference table of discrete rules features."""

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.enums import AbilityScoreType, FeatureSourceTypeType
from app.settings import settings


class Feature(settings.Base):  # type: ignore
    """
    Reference table of discrete rules features: class/subclass features
    (e.g. 'Rage', 'Sneak Attack', 'Extra Attack'), racial and subrace traits,
    and background features. ``source_type`` + the relevant FK
    indicate where the feature comes from; ``level`` is only meaningful for
    CLASS / SUBCLASS features. Feats grant no features (a feat is de facto
    its own feature).
    """

    __tablename__ = "features"

    id = Column(Integer, primary_key=True)

    name = Column(String(200), nullable=False, index=True)
    source_type = Column(FeatureSourceTypeType, nullable=False)

    # Populated depending on source_type; nullable since only one applies per row.
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=True, index=True)
    subclass_id = Column(Integer, ForeignKey("subclasses.id", ondelete="CASCADE"), nullable=True, index=True)

    race_id = Column(Integer, ForeignKey("races.id", ondelete="CASCADE"), nullable=True, index=True)
    subrace_id = Column(Integer, ForeignKey("subraces.id", ondelete="CASCADE"), nullable=True, index=True)

    background_id = Column(Integer, ForeignKey("backgrounds.id", ondelete="CASCADE"), nullable=True, index=True)

    # Only relevant when source_type is CLASS or SUBCLASS: the class level at
    # which the feature is gained (e.g. Extra Attack at level 5).
    level = Column(Integer, nullable=True)

    description = Column(Text, nullable=False, default="")

    character_class = relationship("Class")
    subclass = relationship("Subclass", back_populates="features")
    race = relationship("Race", back_populates="features")
    subrace = relationship("Subrace", back_populates="features")
    background = relationship("Background", back_populates="features")

    # Fixed ability-score effects granted while this feature is on a
    # character (e.g. Primal Champion: STR +4 with cap 24). Purely
    # automatic — no player choice involved; counted by the ability-score
    # calculator for as long as the feature grant exists.
    ability_increases = relationship(
        "FeatureAbilityIncrease",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FeatureAbilityIncrease.id",
    )

    def __repr__(self):
        return f"<Feature(id={self.id}, name='{self.name}', source_type='{self.source_type}')>"


class FeatureAbilityIncrease(settings.Base):  # type: ignore
    """
    A fixed ability-score effect of a Feature, applied automatically for
    every character the feature is granted to (via ``character_features``).

    ``amount`` is added to the effective total (may be negative). When
    ``new_cap`` is set it RAISES (never lowers) that ability's maximum
    score above the standard 20 — e.g. Primal Champion's "max 24 for STR
    and CON" is modeled as two rows with ``amount=4, new_cap=24``.
    """

    __tablename__ = "feature_ability_increases"

    id = Column(Integer, primary_key=True)
    feature_id = Column(Integer, ForeignKey("features.id", ondelete="CASCADE"), nullable=False, index=True)

    ability = Column(AbilityScoreType, nullable=False)
    amount = Column(Integer, nullable=False)
    new_cap = Column(Integer, nullable=True)

    feature = relationship("Feature", back_populates="ability_increases")

    def __repr__(self):
        return (
            f"<FeatureAbilityIncrease(feature_id={self.feature_id}, "
            f"ability='{self.ability}', amount={self.amount}, new_cap={self.new_cap})>"
        )
