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
set — enforced by a ``CheckConstraint`` on each table. The speed and AC
tables have a third possible parent, ``item_id``: an effect of a catalog
item, applied while a character has the item equipped (and attuned, when
the item requires attunement).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    ForeignKey,
    Integer,
    false,
    inspect,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import (
    EFFECT_TYPE_BY_CHOICE_TYPE,
    AbilityScore,
    ArmorClassEffectMode,
    ArmorProficiency,
    ChoiceType,
    EffectCondition,
    SkillEffectMode,
    SpeedEffectMode,
    SpeedType,
    SpellLevel,
    SpellSchool,
    ToolCategory,
    WeaponProficiency,
)
from app.models.enums import (
    AbilityScoreType,
    ArmorClassEffectModeType,
    ArmorProficiencyType,
    ChoiceTypeType,
    EffectConditionType,
    SkillEffectModeType,
    SpeedEffectModeType,
    SpeedTypeType,
    SpellLevelType,
    SpellSchoolType,
    ToolCategoryType,
    WeaponProficiencyType,
)
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.classes.class_model import Class
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
    ("tool", "tool_effects"),
    ("spell", "spell_effects"),
    ("speed", "speed_effects"),
    ("armor_class", "armor_class_effects"),
)

# The effect relationships a ``FeatureChoiceOption`` has: those a ``ChoiceType`` carries (no speed / AC).
CHOICE_OPTION_EFFECT_ATTRS: tuple[str, ...] = tuple(
    attr for effect_type, attr in EFFECT_TYPES if effect_type in EFFECT_TYPE_BY_CHOICE_TYPE.values()
)

# The effect types a catalog item may own (``item_id`` parent), applied while the item is equipped.
ITEM_EFFECT_TYPES: tuple[tuple[str, str], ...] = (
    ("speed", "speed_effects"),
    ("armor_class", "armor_class_effects"),
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

# The parent of a fixed-only effect an item may also own: a feature or an item, never a choice option.
_ITEM_EFFECT_PARENT_CONSTRAINT = "num_nonnulls(feature_id, item_id) = 1 AND choice_option_id IS NULL"


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
    tool_effects: Mapped[list[FeatureToolProficiencyEffect]] = relationship(
        primaryjoin="FeatureChoiceOption.id == FeatureToolProficiencyEffect.choice_option_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    spell_effects: Mapped[list[FeatureSpellGrantEffect]] = relationship(
        primaryjoin="FeatureChoiceOption.id == FeatureSpellGrantEffect.choice_option_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def speed_effects(self) -> list[FeatureSpeedEffect]:
        """Always empty: no choice type carries speed effects (a plain property, so nothing loads it)."""

        return []

    @property
    def armor_class_effects(self) -> list[FeatureArmorClassEffect]:
        """Always empty: no choice type carries AC effects (a plain property, so nothing loads it)."""

        return []

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

    ``ability`` NULL means "any ability" (an open effect, choice options
    only): the player names the ability when picking the option, stored as
    ``CharacterFeatureChoice.picked_ability``. An option carries at most one
    open ability effect.
    """

    __tablename__ = "feature_ability_score_effects"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[int | None] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    choice_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"), index=True
    )

    ability: Mapped[AbilityScore | None] = mapped_column(AbilityScoreType)
    amount: Mapped[int] = mapped_column()
    new_cap: Mapped[int | None] = mapped_column()

    __table_args__ = (
        CheckConstraint(_EFFECT_PARENT_CONSTRAINT, name="ck_feature_ability_score_effect_parent"),
        # Bound = MAX_ABILITY_AMOUNT of the effects schema.
        CheckConstraint("amount BETWEEN -30 AND 30", name="ck_feature_ability_score_effect_amount"),
        CheckConstraint(
            "feature_id IS NULL OR ability IS NOT NULL", name="ck_feature_ability_score_fixed_requires_ability"
        ),
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
    Grants proficiency and/or expertise in a skill, as ``mode`` says (see
    ``SkillEffectMode``).

    ``skill_id`` NULL means "any skill" (an open effect, choice options
    only — a fixed one is invalid): the player names the skill when picking
    the option, stored as ``CharacterFeatureChoice.picked_skill_id``. An
    option carries at most one open skill effect.
    """

    __tablename__ = "feature_skill_proficiency_effects"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[int | None] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    choice_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"), index=True
    )

    skill_id: Mapped[int | None] = mapped_column(ForeignKey("skills.id", ondelete="RESTRICT"), index=True)
    mode: Mapped[SkillEffectMode] = mapped_column(
        SkillEffectModeType, default=SkillEffectMode.PROFICIENCY, server_default=SkillEffectMode.PROFICIENCY.value
    )

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
            f"choice_option_id={self.choice_option_id}, skill_id={self.skill_id}, mode={self.mode})>"
        )


class FeatureSavingThrowEffect(Base):
    """
    Grants proficiency in a saving throw for the given ability. ``ability``
    NULL means "any saving throw" (open, choice options only), named for the
    pick as ``CharacterFeatureChoice.picked_ability``.
    """

    __tablename__ = "feature_saving_throw_effects"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[int | None] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    choice_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"), index=True
    )

    ability: Mapped[AbilityScore | None] = mapped_column(AbilityScoreType)

    __table_args__ = (
        CheckConstraint(_EFFECT_PARENT_CONSTRAINT, name="ck_feature_saving_throw_effect_parent"),
        CheckConstraint(
            "feature_id IS NULL OR ability IS NOT NULL", name="ck_feature_saving_throw_fixed_requires_ability"
        ),
    )

    feature: Mapped[Feature | None] = relationship(back_populates="saving_throw_effects")
    choice_option: Mapped[FeatureChoiceOption | None] = relationship(back_populates="saving_throw_effects")

    def __repr__(self) -> str:
        return (
            f"<FeatureSavingThrowEffect(feature_id={self.feature_id}, "
            f"choice_option_id={self.choice_option_id}, ability='{self.ability}')>"
        )


class FeatureArmorProficiencyEffect(Base):
    """
    Grants proficiency in an armor category (LIGHT/MEDIUM/HEAVY/SHIELD) **or**
    one concrete armor (``item_id`` pointing at an ``Item`` row) — exactly one
    of the two, like :class:`FeatureWeaponProficiencyEffect`.
    """

    __tablename__ = "feature_armor_proficiency_effects"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[int | None] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    choice_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"), index=True
    )

    armor_type: Mapped[ArmorProficiency | None] = mapped_column(ArmorProficiencyType)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), index=True)

    __table_args__ = (
        CheckConstraint(_EFFECT_PARENT_CONSTRAINT, name="ck_feature_armor_proficiency_effect_parent"),
        CheckConstraint(
            "(armor_type IS NOT NULL AND item_id IS NULL) OR (armor_type IS NULL AND item_id IS NOT NULL)",
            name="ck_feature_armor_proficiency_one_target",
        ),
    )

    feature: Mapped[Feature | None] = relationship(back_populates="armor_effects")
    choice_option: Mapped[FeatureChoiceOption | None] = relationship(back_populates="armor_effects")
    item: Mapped[Item | None] = relationship()

    def __repr__(self) -> str:
        return (
            f"<FeatureArmorProficiencyEffect(feature_id={self.feature_id}, "
            f"choice_option_id={self.choice_option_id}, armor_type='{self.armor_type}', item_id={self.item_id})>"
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


class FeatureToolProficiencyEffect(Base):
    """
    Grants proficiency with one tool (``item_id`` pointing at a ``TOOL`` item).

    ``item_id`` NULL means "any tool" (an open effect, choice options only):
    the player names the tool when picking the option, stored as
    ``CharacterFeatureChoice.picked_item_id``. ``tool_category`` narrows an
    open pick ("any musical instrument"); a concrete effect carries none.
    An option carries at most one open tool effect.
    """

    __tablename__ = "feature_tool_proficiency_effects"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[int | None] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    choice_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"), index=True
    )

    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), index=True)
    tool_category: Mapped[ToolCategory | None] = mapped_column(ToolCategoryType)

    __table_args__ = (
        CheckConstraint(_EFFECT_PARENT_CONSTRAINT, name="ck_feature_tool_proficiency_effect_parent"),
        CheckConstraint(
            "feature_id IS NULL OR item_id IS NOT NULL", name="ck_feature_tool_proficiency_fixed_requires_item"
        ),
        CheckConstraint(
            "item_id IS NULL OR tool_category IS NULL", name="ck_feature_tool_proficiency_filter_open_only"
        ),
    )

    feature: Mapped[Feature | None] = relationship(back_populates="tool_effects")
    choice_option: Mapped[FeatureChoiceOption | None] = relationship(back_populates="tool_effects")
    item: Mapped[Item | None] = relationship()

    def __repr__(self) -> str:
        return (
            f"<FeatureToolProficiencyEffect(feature_id={self.feature_id}, "
            f"choice_option_id={self.choice_option_id}, item_id={self.item_id}, tool_category={self.tool_category})>"
        )


class FeatureSpellGrantEffect(Base):
    """
    Grants a spell to the character.

    ``spell_id`` NULL means "any spell" (an open effect, choice options only —
    a fixed one is invalid): an extra spell the player picks when picking the
    option, stored as ``CharacterFeatureChoice.picked_spell_id``. The filter
    columns narrow what may be picked (all of them must hold; an empty list /
    NULL / ``False`` doesn't restrict):

    - ``class_ids`` — the spell is on one of these classes' lists (a spell with
      no class restriction counts as on every list);
    - ``min_level`` / ``max_level`` — the spell level range (cantrips included);
    - ``castable_only`` — a cantrip or a level the character has spell slots of
      (Magical Secrets: "a level you can cast");
    - ``schools`` — one of these schools;
    - ``ritual_only`` — a ritual.

    A concrete effect (``spell_id`` set) carries no filter. An option carries at
    most one open spell effect.
    """

    __tablename__ = "feature_spell_grant_effects"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[int | None] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    choice_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"), index=True
    )

    spell_id: Mapped[int | None] = mapped_column(ForeignKey("spells.id", ondelete="RESTRICT"), index=True)

    # Filters of an open effect (see the class docstring).
    class_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list, server_default=text("'{}'"))
    min_level: Mapped[SpellLevel | None] = mapped_column(SpellLevelType)
    max_level: Mapped[SpellLevel | None] = mapped_column(SpellLevelType)
    castable_only: Mapped[bool] = mapped_column(default=False, server_default=false())
    schools: Mapped[list[SpellSchool]] = mapped_column(
        ARRAY(SpellSchoolType), default=list, server_default=text("'{}'")
    )
    ritual_only: Mapped[bool] = mapped_column(default=False, server_default=false())

    __table_args__ = (CheckConstraint(_EFFECT_PARENT_CONSTRAINT, name="ck_feature_spell_grant_effect_parent"),)

    feature: Mapped[Feature | None] = relationship(back_populates="spell_effects")
    choice_option: Mapped[FeatureChoiceOption | None] = relationship(back_populates="spell_effects")
    # The classes of ``class_ids`` (view-only, joined over the array) — for their names in the filter text.
    filter_classes: Mapped[list[Class]] = relationship(
        primaryjoin="remote(Class.id) == any_(foreign(FeatureSpellGrantEffect.class_ids))",
        viewonly=True,
        uselist=True,
        order_by="Class.name",
    )

    @property
    def class_names(self) -> list[str] | None:
        """Names of the filter's classes when ``filter_classes`` is loaded, else ``None`` (never lazy-loads)."""

        if "filter_classes" in inspect(self).unloaded:
            return None
        return [cls.name.strip() for cls in self.filter_classes]

    spell: Mapped[Spell | None] = relationship()

    def __repr__(self) -> str:
        return (
            f"<FeatureSpellGrantEffect(feature_id={self.feature_id}, "
            f"choice_option_id={self.choice_option_id}, spell_id={self.spell_id})>"
        )


class FeatureSpeedEffect(Base):
    """
    Changes one of the character's speeds, as ``mode`` says (see ``SpeedEffectMode``), while ``condition``
    holds and the character is at least ``min_level``. Owned by a feature or by an item (``item_id``).
    """

    __tablename__ = "feature_speed_effects"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[int | None] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    choice_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)

    speed_type: Mapped[SpeedType] = mapped_column(SpeedTypeType, default=SpeedType.WALK)
    mode: Mapped[SpeedEffectMode] = mapped_column(SpeedEffectModeType, default=SpeedEffectMode.BONUS)
    value: Mapped[int] = mapped_column(default=0)
    condition: Mapped[EffectCondition] = mapped_column(EffectConditionType, default=EffectCondition.NONE)
    min_level: Mapped[int | None] = mapped_column()

    __table_args__ = (
        CheckConstraint(_ITEM_EFFECT_PARENT_CONSTRAINT, name="ck_feature_speed_effect_parent"),
        CheckConstraint("value BETWEEN -200 AND 200", name="ck_feature_speed_effect_value"),
        CheckConstraint("min_level IS NULL OR min_level BETWEEN 1 AND 20", name="ck_feature_speed_effect_min_level"),
    )

    feature: Mapped[Feature | None] = relationship(back_populates="speed_effects")
    item: Mapped[Item | None] = relationship(back_populates="speed_effects")

    def __repr__(self) -> str:
        return (
            f"<FeatureSpeedEffect(feature_id={self.feature_id}, item_id={self.item_id}, "
            f"speed_type={self.speed_type}, mode={self.mode}, value={self.value})>"
        )


class FeatureArmorClassEffect(Base):
    """
    Changes the character's armor class, as ``mode`` says (see ``ArmorClassEffectMode``), while ``condition``
    holds and the character is at least ``min_level``. ``abilities`` / ``allows_shield`` matter for a
    ``FORMULA`` only. Owned by a feature or by an item (``item_id``).
    """

    __tablename__ = "feature_armor_class_effects"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[int | None] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    choice_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("feature_choice_options.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)

    mode: Mapped[ArmorClassEffectMode] = mapped_column(ArmorClassEffectModeType, default=ArmorClassEffectMode.BONUS)
    value: Mapped[int] = mapped_column(default=0)
    abilities: Mapped[list[AbilityScore]] = mapped_column(
        ARRAY(AbilityScoreType), default=list, server_default=text("'{}'")
    )
    allows_shield: Mapped[bool] = mapped_column(default=True, server_default=true())
    condition: Mapped[EffectCondition] = mapped_column(EffectConditionType, default=EffectCondition.NONE)
    min_level: Mapped[int | None] = mapped_column()

    __table_args__ = (
        CheckConstraint(_ITEM_EFFECT_PARENT_CONSTRAINT, name="ck_feature_armor_class_effect_parent"),
        CheckConstraint("value BETWEEN -30 AND 30", name="ck_feature_armor_class_effect_value"),
        CheckConstraint(
            "min_level IS NULL OR min_level BETWEEN 1 AND 20", name="ck_feature_armor_class_effect_min_level"
        ),
    )

    feature: Mapped[Feature | None] = relationship(back_populates="armor_class_effects")
    item: Mapped[Item | None] = relationship(back_populates="armor_class_effects")

    def __repr__(self) -> str:
        return (
            f"<FeatureArmorClassEffect(feature_id={self.feature_id}, item_id={self.item_id}, "
            f"mode={self.mode}, value={self.value})>"
        )
