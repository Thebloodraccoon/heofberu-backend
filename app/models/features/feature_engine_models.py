"""
ORM models for the unified Feature/Feat effect engine (Phase 1 of the feature-engine plan).

Every ``Feature`` may carry any number of typed effects. An effect is
either **fixed** (applied automatically for as long as the grant exists) or
belongs to a **choice option** (applied only when the player selected that
option). Every choice group is pinned to exactly one ``ChoiceType`` (see
``app.constants``) — every option inside it may only populate the one
effect table that type allows (e.g. a ``SKILL`` group's options may only
carry ``feature_skill_proficiency_effects`` rows), enforced on write by
``ChoiceGroupPayload``'s validator.

All effect tables share one invariant — exactly one of ``feature_id``
(fixed effect) or ``choice_option_id`` (effect inside a choice option) is
set — enforced by a ``CheckConstraint`` on each table.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
)
from sqlalchemy.orm import relationship

from app.models.enums import (
    AbilityScoreType,
    ArmorProficiencyType,
    ChoiceTypeType,
    WeaponProficiencyType,
)
from app.settings import settings

# "Exactly one of the two parents" invariant shared by every effect table.
_EFFECT_PARENT_CONSTRAINT = """
    (feature_id IS NOT NULL AND choice_option_id IS NULL)
    OR (feature_id IS NULL AND choice_option_id IS NOT NULL)
"""


class FeatureChoiceGroup(settings.Base):  # type: ignore
    """
    A "pick N of M" decision a player must make when a grant arrives.

    Mirrors ``SourceItemChoiceGroup`` for starting equipment: ``pick_count``
    options must be selected from the group's ``options`` before the grant
    is fully materialized. A feature with no choice groups is purely fixed —
    all of its ``feature_id``-owned effects apply immediately.
    """

    __tablename__ = "feature_choice_groups"

    id = Column(Integer, primary_key=True)
    feature_id = Column(Integer, ForeignKey("features.id", ondelete="CASCADE"), nullable=False, index=True)

    pick_count = Column(Integer, nullable=False, default=1)
    sort_order = Column(Integer, nullable=False, default=0)
    choice_type = Column(ChoiceTypeType, nullable=False)

    __table_args__ = (CheckConstraint("pick_count >= 1", name="check_feature_choice_group_pick_count_positive"),)

    feature = relationship("Feature", back_populates="choice_groups")
    options = relationship(
        "FeatureChoiceOption",
        back_populates="group",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FeatureChoiceOption.sort_order",
    )

    def __repr__(self):
        return f"<FeatureChoiceGroup(id={self.id}, feature_id={self.feature_id}, pick_count={self.pick_count})>"


class FeatureChoiceOption(settings.Base):  # type: ignore
    """
    One option inside a :class:`FeatureChoiceGroup`.

    The option is a *bundle*: all of its child effect rows apply together
    when the option is selected. It carries no label of its own — what it
    grants is fully described by its effect rows, rendered on read (see
    ``app.features.features.effects.rendering``); the group's own
    ``label`` still names the overall decision.
    """

    __tablename__ = "feature_choice_options"

    id = Column(Integer, primary_key=True)
    group_id = Column(
        Integer,
        ForeignKey("feature_choice_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sort_order = Column(Integer, nullable=False, default=0)

    group = relationship("FeatureChoiceGroup", back_populates="options")

    ability_effects = relationship(
        "FeatureAbilityScoreEffect",
        primaryjoin="FeatureChoiceOption.id == FeatureAbilityScoreEffect.choice_option_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    skill_effects = relationship(
        "FeatureSkillProficiencyEffect",
        primaryjoin="FeatureChoiceOption.id == FeatureSkillProficiencyEffect.choice_option_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    saving_throw_effects = relationship(
        "FeatureSavingThrowEffect",
        primaryjoin="FeatureChoiceOption.id == FeatureSavingThrowEffect.choice_option_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    armor_effects = relationship(
        "FeatureArmorProficiencyEffect",
        primaryjoin="FeatureChoiceOption.id == FeatureArmorProficiencyEffect.choice_option_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    weapon_effects = relationship(
        "FeatureWeaponProficiencyEffect",
        primaryjoin="FeatureChoiceOption.id == FeatureWeaponProficiencyEffect.choice_option_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    spell_effects = relationship(
        "FeatureSpellGrantEffect",
        primaryjoin="FeatureChoiceOption.id == FeatureSpellGrantEffect.choice_option_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<FeatureChoiceOption(id={self.id}, group_id={self.group_id})>"


class FeatureAbilityScoreEffect(settings.Base):  # type: ignore
    """
    An ability-score effect: ``amount`` added to an ability's effective total
    (may be negative), optionally raising that ability's cap via ``new_cap``.
    """

    __tablename__ = "feature_ability_score_effects"

    id = Column(Integer, primary_key=True)
    feature_id = Column(Integer, ForeignKey("features.id", ondelete="CASCADE"), nullable=True, index=True)
    choice_option_id = Column(
        Integer,
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    ability = Column(AbilityScoreType, nullable=False)
    amount = Column(Integer, nullable=False)
    new_cap = Column(Integer, nullable=True)

    __table_args__ = (CheckConstraint(_EFFECT_PARENT_CONSTRAINT, name="ck_feature_ability_score_effect_parent"),)

    feature = relationship("Feature", back_populates="ability_effects")
    choice_option = relationship("FeatureChoiceOption", back_populates="ability_effects")

    def __repr__(self):
        return (
            f"<FeatureAbilityScoreEffect(feature_id={self.feature_id}, "
            f"choice_option_id={self.choice_option_id}, ability='{self.ability}', amount={self.amount})>"
        )


class FeatureSkillProficiencyEffect(settings.Base):  # type: ignore
    """
    Grants proficiency (optionally expertise) in a skill.

    ``skill_id`` NULL means "any skill": inside a choice option the usable
    options are computed in the admin UI (one per known skill) rather than
    stored as rows; for a fixed effect a NULL ``skill_id`` is invalid.
    """

    __tablename__ = "feature_skill_proficiency_effects"

    id = Column(Integer, primary_key=True)
    feature_id = Column(Integer, ForeignKey("features.id", ondelete="CASCADE"), nullable=True, index=True)
    choice_option_id = Column(
        Integer,
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    skill_id = Column(Integer, ForeignKey("skills.id", ondelete="RESTRICT"), nullable=True, index=True)
    grants_expertise = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        CheckConstraint(_EFFECT_PARENT_CONSTRAINT, name="ck_feature_skill_proficiency_effect_parent"),
        CheckConstraint(
            "feature_id IS NULL OR skill_id IS NOT NULL",
            name="ck_feature_skill_proficiency_fixed_requires_skill",
        ),
    )

    feature = relationship("Feature", back_populates="skill_effects")
    choice_option = relationship("FeatureChoiceOption", back_populates="skill_effects")
    skill = relationship("Skill")

    def __repr__(self):
        return (
            f"<FeatureSkillProficiencyEffect(feature_id={self.feature_id}, "
            f"choice_option_id={self.choice_option_id}, skill_id={self.skill_id})>"
        )


class FeatureSavingThrowEffect(settings.Base):  # type: ignore
    """Grants proficiency in a saving throw for the given ability."""

    __tablename__ = "feature_saving_throw_effects"

    id = Column(Integer, primary_key=True)
    feature_id = Column(Integer, ForeignKey("features.id", ondelete="CASCADE"), nullable=True, index=True)
    choice_option_id = Column(
        Integer,
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    ability = Column(AbilityScoreType, nullable=False)

    __table_args__ = (CheckConstraint(_EFFECT_PARENT_CONSTRAINT, name="ck_feature_saving_throw_effect_parent"),)

    feature = relationship("Feature", back_populates="saving_throw_effects")
    choice_option = relationship("FeatureChoiceOption", back_populates="saving_throw_effects")

    def __repr__(self):
        return (
            f"<FeatureSavingThrowEffect(feature_id={self.feature_id}, "
            f"choice_option_id={self.choice_option_id}, ability='{self.ability}')>"
        )


class FeatureArmorProficiencyEffect(settings.Base):  # type: ignore
    """Grants proficiency in an armor category (LIGHT/MEDIUM/HEAVY/SHIELD)."""

    __tablename__ = "feature_armor_proficiency_effects"

    id = Column(Integer, primary_key=True)
    feature_id = Column(Integer, ForeignKey("features.id", ondelete="CASCADE"), nullable=True, index=True)
    choice_option_id = Column(
        Integer,
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    armor_type = Column(ArmorProficiencyType, nullable=False)

    __table_args__ = (CheckConstraint(_EFFECT_PARENT_CONSTRAINT, name="ck_feature_armor_proficiency_effect_parent"),)

    feature = relationship("Feature", back_populates="armor_effects")
    choice_option = relationship("FeatureChoiceOption", back_populates="armor_effects")

    def __repr__(self):
        return (
            f"<FeatureArmorProficiencyEffect(feature_id={self.feature_id}, "
            f"choice_option_id={self.choice_option_id}, armor_type='{self.armor_type}')>"
        )


class FeatureWeaponProficiencyEffect(settings.Base):  # type: ignore
    """
    Grants proficiency in a weapon category (SIMPLE/MARTIAL) **or** a single
    concrete weapon (``item_id`` pointing at an ``Item`` row, e.g. the Elf's
    longsword) — exactly one of the two.

    The per-item column is required because constitution/phantoms such as
    Elf weapon training and "Heavy Armor Master" style narrow grants have no
    category equivalent.
    """

    __tablename__ = "feature_weapon_proficiency_effects"

    id = Column(Integer, primary_key=True)
    feature_id = Column(Integer, ForeignKey("features.id", ondelete="CASCADE"), nullable=True, index=True)
    choice_option_id = Column(
        Integer,
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    weapon_category = Column(WeaponProficiencyType, nullable=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=True, index=True)

    __table_args__ = (
        CheckConstraint(_EFFECT_PARENT_CONSTRAINT, name="ck_feature_weapon_proficiency_effect_parent"),
        CheckConstraint(
            "(weapon_category IS NOT NULL AND item_id IS NULL) OR (weapon_category IS NULL AND item_id IS NOT NULL)",
            name="ck_feature_weapon_proficiency_one_target",
        ),
    )

    feature = relationship("Feature", back_populates="weapon_effects")
    choice_option = relationship("FeatureChoiceOption", back_populates="weapon_effects")
    item = relationship("Item")

    def __repr__(self):
        return (
            f"<FeatureWeaponProficiencyEffect(feature_id={self.feature_id}, "
            f"choice_option_id={self.choice_option_id}, weapon_category='{self.weapon_category}', "
            f"item_id={self.item_id})>"
        )


class FeatureSpellGrantEffect(settings.Base):  # type: ignore
    """
    Grants a spell to the character.

    ``spell_id`` NULL means an open choice: the player may pick any spell
    from the catalog at choice time, unconstrained.
    """

    __tablename__ = "feature_spell_grant_effects"

    id = Column(Integer, primary_key=True)
    feature_id = Column(Integer, ForeignKey("features.id", ondelete="CASCADE"), nullable=True, index=True)
    choice_option_id = Column(
        Integer,
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    spell_id = Column(Integer, ForeignKey("spells.id", ondelete="RESTRICT"), nullable=True, index=True)

    __table_args__ = (CheckConstraint(_EFFECT_PARENT_CONSTRAINT, name="ck_feature_spell_grant_effect_parent"),)

    feature = relationship("Feature", back_populates="spell_effects")
    choice_option = relationship("FeatureChoiceOption", back_populates="spell_effects")
    spell = relationship("Spell")

    def __repr__(self):
        return (
            f"<FeatureSpellGrantEffect(feature_id={self.feature_id}, "
            f"choice_option_id={self.choice_option_id}, spell_id={self.spell_id})>"
        )
