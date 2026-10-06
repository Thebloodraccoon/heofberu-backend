"""ORM models for the reference table of discrete rules features."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import AbilityScore, FeatureSourceType
from app.features.features.effects.rendering import render_effects_summary
from app.models.enums import AbilityScoreType, FeatureSourceTypeType
from app.models.features.feature_engine_models import effect_groups
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.backgrounds.background_model import Background
    from app.models.classes.class_model import Class
    from app.models.classes.subclass_model import Subclass
    from app.models.features.feature_engine_models import (
        FeatureAbilityScoreEffect,
        FeatureArmorProficiencyEffect,
        FeatureChoiceGroup,
        FeatureSavingThrowEffect,
        FeatureSkillProficiencyEffect,
        FeatureSpellGrantEffect,
        FeatureWeaponProficiencyEffect,
    )
    from app.models.races.race_model import Race
    from app.models.races.subrace_model import Subrace


class Feature(Base):
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

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(200), index=True)
    source_type: Mapped[FeatureSourceType] = mapped_column(FeatureSourceTypeType)

    # Populated depending on source_type; nullable since only one applies per row.
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    subclass_id: Mapped[int | None] = mapped_column(ForeignKey("subclasses.id", ondelete="CASCADE"), index=True)

    race_id: Mapped[int | None] = mapped_column(ForeignKey("races.id", ondelete="CASCADE"), index=True)
    subrace_id: Mapped[int | None] = mapped_column(ForeignKey("subraces.id", ondelete="CASCADE"), index=True)

    background_id: Mapped[int | None] = mapped_column(ForeignKey("backgrounds.id", ondelete="CASCADE"), index=True)

    # Only relevant when source_type is CLASS or SUBCLASS: the class level at
    # which the feature is gained (e.g. Extra Attack at level 5).
    level: Mapped[int | None] = mapped_column()

    description: Mapped[str] = mapped_column(Text, default="")

    # -- Feat fields (only meaningful when source_type == FEAT) ---------------
    # Minimum character level required to take this feat (e.g. level 4+
    # feats). NULL = no level requirement. Migrated from ``Feat.min_level``.
    min_level: Mapped[int | None] = mapped_column()

    # Structured prerequisite, e.g. "STR 13" for Heavy Armor Master.
    # Both NULL when the feat has no ability-score prerequisite.
    prerequisite_ability: Mapped[AbilityScore | None] = mapped_column(AbilityScoreType)
    prerequisite_minimum_score: Mapped[int | None] = mapped_column()

    # Free-text prerequisite for non-numeric requirements not otherwise
    # modeled, e.g. "The ability to cast at least one spell".
    prerequisite_description: Mapped[str] = mapped_column(Text, default="")

    # Denormalized off the effect/choice-group tables: refreshed by every write
    # path that touches them (``FeatureEffectsService``,
    # ``FeatRepository.set_ability_score_increases``), never computed on read,
    # so listings can column-select them instead of loading the effect tree.
    has_static_effects: Mapped[bool] = mapped_column(default=False, server_default="false")
    has_choices: Mapped[bool] = mapped_column(default=False, server_default="false")

    character_class: Mapped[Class | None] = relationship()
    subclass: Mapped[Subclass | None] = relationship(back_populates="features")
    race: Mapped[Race | None] = relationship(back_populates="features")
    subrace: Mapped[Subrace | None] = relationship(back_populates="features")
    background: Mapped[Background | None] = relationship(back_populates="features")

    # Any number of choice groups ("pick N of M") and their options; each
    # option is a bundle of effects applied together.
    choice_groups: Mapped[list[FeatureChoiceGroup]] = relationship(
        back_populates="feature",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FeatureChoiceGroup.sort_order",
    )

    # Fixed (non-choice) effects, one child table per effect kind. Each row
    # holds ``feature_id`` here (the alternative ``choice_option_id`` lives on
    # the same tables; a CheckConstraint enforces exactly one of the two).
    ability_effects: Mapped[list[FeatureAbilityScoreEffect]] = relationship(
        primaryjoin="Feature.id == FeatureAbilityScoreEffect.feature_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    skill_effects: Mapped[list[FeatureSkillProficiencyEffect]] = relationship(
        primaryjoin="Feature.id == FeatureSkillProficiencyEffect.feature_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    saving_throw_effects: Mapped[list[FeatureSavingThrowEffect]] = relationship(
        primaryjoin="Feature.id == FeatureSavingThrowEffect.feature_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    armor_effects: Mapped[list[FeatureArmorProficiencyEffect]] = relationship(
        primaryjoin="Feature.id == FeatureArmorProficiencyEffect.feature_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    weapon_effects: Mapped[list[FeatureWeaponProficiencyEffect]] = relationship(
        primaryjoin="Feature.id == FeatureWeaponProficiencyEffect.feature_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    spell_effects: Mapped[list[FeatureSpellGrantEffect]] = relationship(
        primaryjoin="Feature.id == FeatureSpellGrantEffect.feature_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def static_groups(self) -> list[dict]:
        """
        This feature's fixed effects as non-empty effect groups, for
        ``FeatureResponse``/``NestedFeatureResponse``'s ``static_groups`` field
        (see :func:`~app.models.features.feature_engine_models.effect_groups`).
        """

        return effect_groups(self)

    @property
    def effects_summary(self) -> str:
        """Human-readable summary of this feature's fixed effects and choice groups (see ``rendering.py``)."""

        return render_effects_summary(self)

    def __repr__(self) -> str:
        return f"<Feature(id={self.id}, name='{self.name}', source_type='{self.source_type}')>"
