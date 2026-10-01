"""ORM models for the reference table of discrete rules features."""

from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import relationship

from app.features.features.effects.rendering import render_effects_summary
from app.models.enums import AbilityScoreType, FeatureSourceTypeType
from app.settings import settings


class Feature(settings.Base):  # type: ignore
    """
    Reference table of discrete rules features: class/subclass features
    (e.g. 'Rage', 'Sneak Attack', 'Extra Attack'), racial and subrace traits,
    background features, AND feats (``source_type=FEAT``).

    ``source_type`` + the relevant FK indicate where the feature comes from;
    ``level`` is only meaningful for CLASS / SUBCLASS features. A
    ``FEAT``-source row carries NO source FK (all nullable) and instead holds
    the feat-specific ``min_level`` / ``prerequisite_*`` columns. The
    distinction "class grants it automatically" vs "player picks it as a
    feat" is not a difference in entity type — it lives in how the grant
    arrives on the character (``grant_source`` on ``character_features``).
    """

    __tablename__ = "features"
    __table_args__ = (
        # A feat is addressed by name: unique among FEAT rows only (class/race/... features may repeat names).
        Index("uq_features_feat_name", "name", unique=True, postgresql_where=text("source_type = 'FEAT'")),
    )

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

    # -- Feat fields (only meaningful when source_type == FEAT) ---------------
    # Minimum character level required to take this feat (e.g. level 4+
    # feats). NULL = no level requirement. Migrated from ``Feat.min_level``.
    min_level = Column(Integer, nullable=True)

    # Structured prerequisite, e.g. "STR 13" for Heavy Armor Master.
    # Both NULL when the feat has no ability-score prerequisite.
    prerequisite_ability = Column(AbilityScoreType, nullable=True)
    prerequisite_minimum_score = Column(Integer, nullable=True)

    # Free-text prerequisite for non-numeric requirements not otherwise
    # modeled, e.g. "The ability to cast at least one spell".
    prerequisite_description = Column(Text, nullable=False, default="")

    # Denormalized off the effect/choice-group tables: refreshed by every write
    # path that touches them (``FeatureEffectsService``,
    # ``FeatRepository.set_ability_score_increases``), never computed on read,
    # so listings can column-select them instead of loading the effect tree.
    has_static_effects = Column(Boolean, nullable=False, default=False, server_default="false")
    has_choices = Column(Boolean, nullable=False, default=False, server_default="false")

    character_class = relationship("Class")
    subclass = relationship("Subclass", back_populates="features")
    race = relationship("Race", back_populates="features")
    subrace = relationship("Subrace", back_populates="features")
    background = relationship("Background", back_populates="features")

    # Any number of choice groups ("pick N of M") and their options; each
    # option is a bundle of effects applied together.
    choice_groups = relationship(
        "FeatureChoiceGroup",
        back_populates="feature",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FeatureChoiceGroup.sort_order",
    )

    # Fixed (non-choice) effects, one child table per effect kind. Each row
    # holds ``feature_id`` here (the alternative ``choice_option_id`` lives on
    # the same tables; a CheckConstraint enforces exactly one of the two).
    ability_effects = relationship(
        "FeatureAbilityScoreEffect",
        primaryjoin="Feature.id == FeatureAbilityScoreEffect.feature_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    skill_effects = relationship(
        "FeatureSkillProficiencyEffect",
        primaryjoin="Feature.id == FeatureSkillProficiencyEffect.feature_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    saving_throw_effects = relationship(
        "FeatureSavingThrowEffect",
        primaryjoin="Feature.id == FeatureSavingThrowEffect.feature_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    armor_effects = relationship(
        "FeatureArmorProficiencyEffect",
        primaryjoin="Feature.id == FeatureArmorProficiencyEffect.feature_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    weapon_effects = relationship(
        "FeatureWeaponProficiencyEffect",
        primaryjoin="Feature.id == FeatureWeaponProficiencyEffect.feature_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    spell_effects = relationship(
        "FeatureSpellGrantEffect",
        primaryjoin="Feature.id == FeatureSpellGrantEffect.feature_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def static_groups(self) -> list[dict]:
        """
        This feature's fixed effects grouped by kind (one entry per non-empty
        effect relationship), for ``FeatureResponse``/``NestedFeatureResponse``'s
        ``static_groups`` field — see ``StaticEffectGroup`` in
        ``app.features.features.effects.schemas``.
        """

        groups = [
            ("ability", self.ability_effects),
            ("skill", self.skill_effects),
            ("saving_throw", self.saving_throw_effects),
            ("armor", self.armor_effects),
            ("weapon", self.weapon_effects),
            ("spell", self.spell_effects),
        ]
        return [{"effect_type": effect_type, "items": items} for effect_type, items in groups if items]

    @property
    def effects_summary(self) -> str:
        """Human-readable summary of this feature's fixed effects and choice groups (see ``rendering.py``)."""

        return render_effects_summary(self)

    def __repr__(self):
        return f"<Feature(id={self.id}, name='{self.name}', source_type='{self.source_type}')>"
