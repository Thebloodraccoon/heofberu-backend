"""ORM models for feats and their ability-score-increase options."""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.enums import AbilityScoreType
from app.settings import settings


class Feat(settings.Base):  # type: ignore
    """
    Reference table of feats (e.g. Alert, Heavy Armor Master), shared
    across all characters. GM-managed, like Race, Class and Spell.

    Classic 5e feats are typically taken instead of an Ability Score
    Improvement, and some feats additionally grant their own ability
    score increase as part of the feat's effect (e.g. Resilient).
    """

    __tablename__ = "feats"

    id = Column(Integer, primary_key=True)

    name = Column(String(200), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=False, default="")

    # Structured prerequisite, e.g. "STR 13" for Heavy Armor Master.
    # Both NULL when the feat has no ability-score prerequisite.
    prerequisite_ability = Column(AbilityScoreType, nullable=True)
    prerequisite_minimum_score = Column(Integer, nullable=True)

    # Free-text prerequisite for non-numeric requirements not otherwise
    # modeled, e.g. "The ability to cast at least one spell" or
    # "Proficiency with heavy armor". Independent of the structured
    # prerequisite above; either or both may be set.
    prerequisite_description = Column(Text, nullable=False, default="")

    is_homebrew = Column(Boolean, nullable=False, default=False)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Some feats grant an ability score increase as part of their effect
    # (distinct from the ASI a feat is taken in place of). Modeled as
    # child rows rather than a single column so a feat can offer several
    # valid choices, e.g. Resilient ("choose one ability") or an Origin
    # feat offering "+2 one ability, or +1/+1 to two abilities".
    ability_score_increases = relationship(
        "FeatAbilityScoreIncrease",
        back_populates="feat",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # FEAT-source features granted by this feat (e.g. Alert's "can't be
    # surprised while conscious"). Created nested in the same request as
    # the feat and automatically granted to any character holding it —
    # see ``sync_progression_features``.
    features = relationship(
        "Feature",
        back_populates="feat",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Feature.id",
    )

    created_by = relationship("User")

    def __repr__(self):
        return f"<Feat(id={self.id}, name='{self.name}')>"


class FeatAbilityScoreIncrease(settings.Base):  # type: ignore
    """
    A single ability-score-increase option granted by a Feat. A feat with
    no rows here grants no ASI of its own. Multiple rows on the same feat
    represent alternative abilities the player may choose between (not
    increases applied simultaneously), e.g. Resilient's "choose one"
    or an Origin feat's "+1 to two of the following abilities".
    """

    __tablename__ = "feat_ability_score_increases"

    id = Column(Integer, primary_key=True)
    feat_id = Column(Integer, ForeignKey("feats.id", ondelete="CASCADE"), nullable=False, index=True)

    ability = Column(AbilityScoreType, nullable=False)
    amount = Column(Integer, nullable=False, default=1)

    feat = relationship("Feat", back_populates="ability_score_increases")

    def __repr__(self):
        return f"<FeatAbilityScoreIncrease(feat_id={self.feat_id}, ability='{self.ability}', amount={self.amount})>"
