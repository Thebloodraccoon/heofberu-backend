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

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import AbilityScore, ArmorProficiency, ChoiceType, WeaponProficiency
from app.models.enums import (
    AbilityScoreType,
    ArmorProficiencyType,
    ChoiceTypeType,
    WeaponProficiencyType,
)
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.features.feature_model import Feature
    from app.models.items.item_model import Item
    from app.models.skill_model import Skill
    from app.models.spells.spell_model import Spell

# ``effect_type`` of each effect group and the relationship that holds its rows, on both
# ``Feature`` (fixed effects) and ``FeatureChoiceOption`` (an option's bundle). The order is
# the order groups are listed in API responses.
EFFECT_TYPES: tuple[tuple[str, str], ...] = (
    ("ability", "ability_effects"),
    ("skill", "skill_effects"),
    ("saving_throw", "saving_throw_effects"),
    ("armor", "armor_effects"),
    ("weapon", "weapon_effects"),
    ("spell", "spell_effects"),
)


def effect_groups(holder: Feature | FeatureChoiceOption) -> list[dict]:
    """
    ``holder``'s effects as ``[{effect_type, items}]``, one entry per NON-EMPTY effect
    relationship — the single API shape of an effect bundle (``EffectGroup`` in
    ``app.features.features.effects.schemas``). The relationships must be loaded.
    """

    return [
        {"effect_type": effect_type, "items": items}
        for effect_type, attr in EFFECT_TYPES
        if (items := getattr(holder, attr))
    ]


# "Exactly one of the two parents" invariant shared by every effect table.
_EFFECT_PARENT_CONSTRAINT = """
    (feature_id IS NOT NULL AND choice_option_id IS NULL)
    OR (feature_id IS NULL AND choice_option_id IS NOT NULL)
"""


class FeatureChoiceGroup(Base):
    """
    A "pick N of M" decision a player must make when a grant arrives.

    Mirrors ``SourceItemChoiceGroup`` for starting equipment: ``pick_count``
    options must be selected from the group's ``options`` before the grant
    is fully materialized. A feature with no choice groups is purely fixed —
    all of its ``feature_id``-owned effects apply immediately.
    """

    __tablename__ = "feature_choice_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[int] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)

    pick_count: Mapped[int] = mapped_column(default=1)
    sort_order: Mapped[int] = mapped_column(default=0)
    choice_type: Mapped[ChoiceType] = mapped_column(ChoiceTypeType)

    __table_args__ = (
        CheckConstraint("pick_count >= 1", name="check_feature_choice_group_pick_count_positive"),
        # Upper bound = MAX_PICK_COUNT of the effects schema.
        CheckConstraint("pick_count <= 50", name="ck_feature_choice_group_pick_count_max"),
    )

    feature: Mapped[Feature] = relationship(back_populates="choice_groups")
    options: Mapped[list[FeatureChoiceOption]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FeatureChoiceOption.sort_order",
    )

    def __repr__(self) -> str:
        return f"<FeatureChoiceGroup(id={self.id}, feature_id={self.feature_id}, pick_count={self.pick_count})>"


class FeatureChoiceOption(Base):
    """
    One option inside a :class:`FeatureChoiceGroup`.

    The option is a *bundle*: all of its child effect rows apply together
    when the option is selected. It carries no label of its own — what it
    grants is fully described by its effect rows, rendered on read (see
    ``app.features.features.effects.rendering``); the group's own
    ``label`` still names the overall decision.
    """

    __tablename__ = "feature_choice_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("feature_choice_groups.id", ondelete="CASCADE"), index=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    group: Mapped[FeatureChoiceGroup] = relationship(back_populates="options")

    ability_effects: Mapped[list[FeatureAbilityScoreEffect]] = relationship(
        primaryjoin="FeatureChoiceOption.id == FeatureAbilityScoreEffect.choice_option_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    skill_effects: Mapped[list[FeatureSkillProficiencyEffect]] = relationship(
        primaryjoin="FeatureChoiceOption.id == FeatureSkillProficiencyEffect.choice_option_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    saving_throw_effects: Mapped[list[FeatureSavingThrowEffect]] = relationship(
        primaryjoin="FeatureChoiceOption.id == FeatureSavingThrowEffect.choice_option_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    armor_effects: Mapped[list[FeatureArmorProficiencyEffect]] = relationship(
        primaryjoin="FeatureChoiceOption.id == FeatureArmorProficiencyEffect.choice_option_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    weapon_effects: Mapped[list[FeatureWeaponProficiencyEffect]] = relationship(
        primaryjoin="FeatureChoiceOption.id == FeatureWeaponProficiencyEffect.choice_option_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    spell_effects: Mapped[list[FeatureSpellGrantEffect]] = relationship(
        primaryjoin="FeatureChoiceOption.id == FeatureSpellGrantEffect.choice_option_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def effects(self) -> list[dict]:
        """This option's bundle as non-empty effect groups (see :func:`effect_groups`)."""

        return effect_groups(self)

    def __repr__(self) -> str:
        return f"<FeatureChoiceOption(id={self.id}, group_id={self.group_id})>"


class FeatureAbilityScoreEffect(Base):
    """
    An ability-score effect: ``amount`` added to an ability's effective total
    (may be negative), optionally raising that ability's cap via ``new_cap``.
    """

    __tablename__ = "feature_ability_score_effects"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[int | None] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    choice_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"), index=True
    )

    ability: Mapped[AbilityScore] = mapped_column(AbilityScoreType)
    amount: Mapped[int] = mapped_column()
    new_cap: Mapped[int | None] = mapped_column()

    __table_args__ = (
        CheckConstraint(_EFFECT_PARENT_CONSTRAINT, name="ck_feature_ability_score_effect_parent"),
        # Bound = MAX_ABILITY_AMOUNT of the effects schema.
        CheckConstraint("amount BETWEEN -30 AND 30", name="ck_feature_ability_score_effect_amount"),
    )

    feature: Mapped[Feature | None] = relationship(back_populates="ability_effects")
    choice_option: Mapped[FeatureChoiceOption | None] = relationship(back_populates="ability_effects")

    def __repr__(self) -> str:
        return (
            f"<FeatureAbilityScoreEffect(feature_id={self.feature_id}, "
            f"choice_option_id={self.choice_option_id}, ability='{self.ability}', amount={self.amount})>"
        )


class FeatureSkillProficiencyEffect(Base):
    """
    Grants proficiency (optionally expertise) in a skill.

    ``skill_id`` NULL means "any skill": inside a choice option the usable
    options are computed in the admin UI (one per known skill) rather than
    stored as rows; for a fixed effect a NULL ``skill_id`` is invalid.
    """

    __tablename__ = "feature_skill_proficiency_effects"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[int | None] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    choice_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"), index=True
    )

    skill_id: Mapped[int | None] = mapped_column(ForeignKey("skills.id", ondelete="RESTRICT"), index=True)
    grants_expertise: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        CheckConstraint(_EFFECT_PARENT_CONSTRAINT, name="ck_feature_skill_proficiency_effect_parent"),
        CheckConstraint(
            "feature_id IS NULL OR skill_id IS NOT NULL",
            name="ck_feature_skill_proficiency_fixed_requires_skill",
        ),
    )

    feature: Mapped[Feature | None] = relationship(back_populates="skill_effects")
    choice_option: Mapped[FeatureChoiceOption | None] = relationship(back_populates="skill_effects")
    skill: Mapped[Skill | None] = relationship()

    def __repr__(self) -> str:
        return (
            f"<FeatureSkillProficiencyEffect(feature_id={self.feature_id}, "
            f"choice_option_id={self.choice_option_id}, skill_id={self.skill_id})>"
        )


class FeatureSavingThrowEffect(Base):
    """Grants proficiency in a saving throw for the given ability."""

    __tablename__ = "feature_saving_throw_effects"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[int | None] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    choice_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"), index=True
    )

    ability: Mapped[AbilityScore] = mapped_column(AbilityScoreType)

    __table_args__ = (CheckConstraint(_EFFECT_PARENT_CONSTRAINT, name="ck_feature_saving_throw_effect_parent"),)

    feature: Mapped[Feature | None] = relationship(back_populates="saving_throw_effects")
    choice_option: Mapped[FeatureChoiceOption | None] = relationship(back_populates="saving_throw_effects")

    def __repr__(self) -> str:
        return (
            f"<FeatureSavingThrowEffect(feature_id={self.feature_id}, "
            f"choice_option_id={self.choice_option_id}, ability='{self.ability}')>"
        )


class FeatureArmorProficiencyEffect(Base):
    """Grants proficiency in an armor category (LIGHT/MEDIUM/HEAVY/SHIELD)."""

    __tablename__ = "feature_armor_proficiency_effects"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[int | None] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    choice_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"), index=True
    )

    armor_type: Mapped[ArmorProficiency] = mapped_column(ArmorProficiencyType)

    __table_args__ = (CheckConstraint(_EFFECT_PARENT_CONSTRAINT, name="ck_feature_armor_proficiency_effect_parent"),)

    feature: Mapped[Feature | None] = relationship(back_populates="armor_effects")
    choice_option: Mapped[FeatureChoiceOption | None] = relationship(back_populates="armor_effects")

    def __repr__(self) -> str:
        return (
            f"<FeatureArmorProficiencyEffect(feature_id={self.feature_id}, "
            f"choice_option_id={self.choice_option_id}, armor_type='{self.armor_type}')>"
        )


class FeatureWeaponProficiencyEffect(Base):
    """
    Grants proficiency in a weapon category (SIMPLE/MARTIAL) **or** a single
    concrete weapon (``item_id`` pointing at an ``Item`` row, e.g. the Elf's
    longsword) — exactly one of the two.

    The per-item column is required because constitution/phantoms such as
    Elf weapon training and "Heavy Armor Master" style narrow grants have no
    category equivalent.
    """

    __tablename__ = "feature_weapon_proficiency_effects"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[int | None] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    choice_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"), index=True
    )

    weapon_category: Mapped[WeaponProficiency | None] = mapped_column(WeaponProficiencyType)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), index=True)

    __table_args__ = (
        CheckConstraint(_EFFECT_PARENT_CONSTRAINT, name="ck_feature_weapon_proficiency_effect_parent"),
        CheckConstraint(
            "(weapon_category IS NOT NULL AND item_id IS NULL) OR (weapon_category IS NULL AND item_id IS NOT NULL)",
            name="ck_feature_weapon_proficiency_one_target",
        ),
    )

    feature: Mapped[Feature | None] = relationship(back_populates="weapon_effects")
    choice_option: Mapped[FeatureChoiceOption | None] = relationship(back_populates="weapon_effects")
    item: Mapped[Item | None] = relationship()

    def __repr__(self) -> str:
        return (
            f"<FeatureWeaponProficiencyEffect(feature_id={self.feature_id}, "
            f"choice_option_id={self.choice_option_id}, weapon_category='{self.weapon_category}', "
            f"item_id={self.item_id})>"
        )


class FeatureSpellGrantEffect(Base):
    """
    Grants a spell to the character.

    ``spell_id`` NULL means an open choice: the player may pick any spell
    from the catalog at choice time, unconstrained.
    """

    __tablename__ = "feature_spell_grant_effects"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[int | None] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    choice_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"), index=True
    )

    spell_id: Mapped[int | None] = mapped_column(ForeignKey("spells.id", ondelete="RESTRICT"), index=True)

    __table_args__ = (CheckConstraint(_EFFECT_PARENT_CONSTRAINT, name="ck_feature_spell_grant_effect_parent"),)

    feature: Mapped[Feature | None] = relationship(back_populates="spell_effects")
    choice_option: Mapped[FeatureChoiceOption | None] = relationship(back_populates="spell_effects")
    spell: Mapped[Spell | None] = relationship()

    def __repr__(self) -> str:
        return (
            f"<FeatureSpellGrantEffect(feature_id={self.feature_id}, "
            f"choice_option_id={self.choice_option_id}, spell_id={self.spell_id})>"
        )
