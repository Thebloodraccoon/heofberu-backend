"""Feature effects capability: request/response schemas for the effect engine (Phase 3)."""

from collections.abc import Callable
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.constants import (
    EFFECT_TYPE_BY_CHOICE_TYPE,
    AbilityScore,
    ArmorProficiency,
    ChoiceType,
    SkillEffectMode,
    SpellLevel,
    SpellSchool,
    WeaponProficiency,
)
from app.core.types import EntityId
from app.features.features.effects.rendering import describe_spell_filter

VALID_NEW_CAP_MIN = 20
VALID_NEW_CAP_MAX = 30

MAX_EFFECTS_PER_LIST = 50
MAX_OPTIONS_PER_GROUP = 50
MAX_CHOICE_GROUPS = 20
MAX_PICK_COUNT = 50
MAX_SORT_ORDER = 10_000
MAX_ABILITY_AMOUNT = 30
MAX_SPELL_FILTER_CLASSES = 20

# Spell levels from cantrip up — the order a spell effect's level range is checked in.
SPELL_LEVEL_ORDER: tuple[SpellLevel, ...] = tuple(SpellLevel)


# What makes two effects of the same type "the same effect" (and so a duplicate).
DUPLICATE_KEY_BY_EFFECT_FIELD: dict[str, Callable[[Any], Any]] = {
    "ability_effects": lambda effect: effect.ability,
    "skill_effects": lambda effect: effect.skill_id,
    "saving_throw_effects": lambda effect: effect.ability,
    "armor_effects": lambda effect: (effect.armor_type, effect.item_id),
    "weapon_effects": lambda effect: (effect.weapon_category, effect.item_id),
    "spell_effects": lambda effect: effect.spell_id,
}
_ALL_OPTION_EFFECT_FIELDS = tuple(DUPLICATE_KEY_BY_EFFECT_FIELD)


def _reject_duplicates(values: list, label: str) -> None:
    """Raise ``ValueError`` naming the first repeated value in ``values``."""

    seen: set = set()
    for value in values:
        if value in seen:
            raise ValueError(f"Duplicate {label}: {getattr(value, 'value', value)}.")
        seen.add(value)


def _validate_effect_lists(model: BaseModel, field_names: tuple[str, ...]) -> None:
    """Reject repeated row ids and repeated effects within each of ``model``'s effect lists."""

    for field_name in field_names:
        items = getattr(model, field_name)
        if not items:
            continue

        _reject_duplicates([item.id for item in items if item.id is not None], f"id in {field_name}")
        key = DUPLICATE_KEY_BY_EFFECT_FIELD[field_name]
        _reject_duplicates([key(item) for item in items], f"entry in {field_name}")


class AbilityEffectItem(BaseModel):
    """
    A fixed/option ability-score effect: ``amount`` added, optional
    ``new_cap`` raise. ``id`` is the DB row id — absent on a write payload,
    present on any response (e.g. a feat's ASI options each need their own
    id so a grant can point ``ability_score_increase_id`` at the one picked).
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: EntityId | None = None
    ability: AbilityScore
    amount: int = Field(ge=-MAX_ABILITY_AMOUNT, le=MAX_ABILITY_AMOUNT)
    new_cap: int | None = None

    @field_validator("new_cap")
    @classmethod
    def validate_new_cap(cls, value):
        """Enforce the new_cap range (20–30) mirroring the legacy ASI validation."""
        if value is not None and not (VALID_NEW_CAP_MIN <= value <= VALID_NEW_CAP_MAX):
            raise ValueError(f"new_cap must be between {VALID_NEW_CAP_MIN} and {VALID_NEW_CAP_MAX}.")
        return value


class SkillEffectItem(BaseModel):
    """
    A fixed/option skill effect: what ``mode`` gives (proficiency,
    expertise or both — see ``SkillEffectMode``) in ``skill_id``.

    ``skill_id=None`` is an open ("any skill") effect, valid in a choice
    option only: the player names the skill when picking the option. A
    fixed effect needs a concrete ``skill_id``, and an option may carry at
    most one open effect (two would repeat the same ``None`` entry).

    ``id`` is the DB row id: present on a response, and the path's ``effect_id``
    for a point write — a new row's payload must not carry one (422).
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: EntityId | None = None
    skill_id: EntityId | None = None
    mode: SkillEffectMode = SkillEffectMode.PROFICIENCY


class SavingThrowEffectItem(BaseModel):
    """A fixed/option saving-throw-proficiency effect. ``id``: see ``SkillEffectItem``."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: EntityId | None = None
    ability: AbilityScore


class ArmorEffectItem(BaseModel):
    """
    A fixed/option armor-proficiency effect: a category OR a concrete armor
    item (``item_id``), exactly one. ``id``: see ``SkillEffectItem``.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: EntityId | None = None
    armor_type: ArmorProficiency | None = None
    item_id: EntityId | None = None

    @model_validator(mode="after")
    def _guard_single_target(self):
        """Guard: exactly one of ``armor_type`` / ``item_id`` must be set."""
        if (self.armor_type is None) == (self.item_id is None):
            raise ValueError("Set exactly one of armor_type or item_id.")
        return self


class WeaponEffectItem(BaseModel):
    """A fixed/option weapon-proficiency effect: a category OR a concrete item. ``id``: see ``SkillEffectItem``."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: EntityId | None = None
    weapon_category: WeaponProficiency | None = None
    item_id: EntityId | None = None

    @model_validator(mode="after")
    def _guard_single_target(self):
        """Guard: exactly one of ``weapon_category`` / ``item_id`` must be set."""
        if (self.weapon_category is None) == (self.item_id is None):
            raise ValueError("Set exactly one of weapon_category or item_id.")
        return self


class SpellEffectItem(BaseModel):
    """
    A fixed/option spell-grant effect: a concrete ``spell_id``, or an open
    ("any spell") effect — ``spell_id`` unset, valid in a choice option only:
    an extra spell the player picks when picking the option (Magical Secrets).

    An open effect's filters narrow what may be picked, all of them at once;
    the defaults don't restrict:

    - ``class_ids`` — on one of these classes' spell lists (a spell with no
      class restriction is on every list);
    - ``min_level`` / ``max_level`` — the level range (``CANTRIP`` included;
      ``min_level == max_level`` is "exactly this level");
    - ``castable_only`` — a cantrip or a level the character has spell slots of;
    - ``schools`` — one of these schools;
    - ``ritual_only`` — a ritual.

    A concrete effect may not carry a filter (422). ``id``: see ``SkillEffectItem``.

    On read an open effect also carries ``summary``: its filter as ready-made
    Russian phrases (``describe_spell_filter``, class names included when the
    row's ``filter_classes`` were loaded) — the one place that text is built.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: EntityId | None = None
    spell_id: EntityId | None = None
    class_ids: list[EntityId] = Field([], max_length=MAX_SPELL_FILTER_CLASSES)
    min_level: SpellLevel | None = None
    max_level: SpellLevel | None = None
    castable_only: bool = False
    schools: list[SpellSchool] = Field([], max_length=len(SpellSchool))
    ritual_only: bool = False
    # Read side only: the filter's class names (``FeatureSpellGrantEffect.class_names``); never written.
    class_names: list[str] | None = Field(None, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def summary(self) -> list[str]:
        """The open effect's filter as phrases (``[]`` for a concrete spell or no filter)."""

        return describe_spell_filter(self) if self.spell_id is None else []

    @field_validator("class_ids", "schools")
    @classmethod
    def _dedupe(cls, values: list) -> list:
        """A filter list is a set: repeats are dropped, order kept."""

        return list(dict.fromkeys(values))

    @property
    def has_filter(self) -> bool:
        """Whether any filter restricts the pick."""

        return bool(
            self.class_ids
            or self.min_level
            or self.max_level
            or self.castable_only
            or self.schools
            or self.ritual_only
        )

    @model_validator(mode="after")
    def _check_filters(self):
        """Filters belong to an open effect only, and the level range must not be inverted."""

        if self.spell_id is not None and self.has_filter:
            raise ValueError("Spell filters apply only to an open ('any spell') effect — leave spell_id unset.")

        if (
            self.min_level is not None
            and self.max_level is not None
            and SPELL_LEVEL_ORDER.index(self.min_level) > SPELL_LEVEL_ORDER.index(self.max_level)
        ):
            raise ValueError("min_level must not be above max_level.")
        return self


class AbilityEffectGroup(BaseModel):
    """Ability-score effects of a bundle, grouped under ``effect_type='ability'``."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    effect_type: Literal["ability"]
    items: list[AbilityEffectItem] = Field([], max_length=MAX_EFFECTS_PER_LIST)


class SkillEffectGroup(BaseModel):
    """Skill-proficiency effects of a bundle, grouped under ``effect_type='skill'``."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    effect_type: Literal["skill"]
    items: list[SkillEffectItem] = Field([], max_length=MAX_EFFECTS_PER_LIST)


class SavingThrowEffectGroup(BaseModel):
    """Saving-throw-proficiency effects of a bundle, grouped under ``effect_type='saving_throw'``."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    effect_type: Literal["saving_throw"]
    items: list[SavingThrowEffectItem] = Field([], max_length=MAX_EFFECTS_PER_LIST)


class ArmorEffectGroup(BaseModel):
    """Armor-proficiency effects of a bundle, grouped under ``effect_type='armor'``."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    effect_type: Literal["armor"]
    items: list[ArmorEffectItem] = Field([], max_length=MAX_EFFECTS_PER_LIST)


class WeaponEffectGroup(BaseModel):
    """Weapon-proficiency effects of a bundle, grouped under ``effect_type='weapon'``."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    effect_type: Literal["weapon"]
    items: list[WeaponEffectItem] = Field([], max_length=MAX_EFFECTS_PER_LIST)


class SpellEffectGroup(BaseModel):
    """Spell-grant effects of a bundle, grouped under ``effect_type='spell'``."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    effect_type: Literal["spell"]
    items: list[SpellEffectItem] = Field([], max_length=MAX_EFFECTS_PER_LIST)


# The one API shape of an effect bundle, read and write alike: a list of these, one entry per
# effect type the bundle carries — a feature's fixed effects (``static_groups``) and a choice
# option's bundle (``effects``). Responses list only non-empty types
# (``app.models.features.feature_engine_models.effect_groups``); ``effect_type`` discriminates.
EffectGroup = Annotated[
    AbilityEffectGroup
    | SkillEffectGroup
    | SavingThrowEffectGroup
    | ArmorEffectGroup
    | WeaponEffectGroup
    | SpellEffectGroup,
    Field(discriminator="effect_type"),
]


EffectType = Literal["ability", "skill", "saving_throw", "armor", "weapon", "spell"]

ITEM_BY_EFFECT_TYPE: dict[str, type[BaseModel]] = {
    "ability": AbilityEffectItem,
    "skill": SkillEffectItem,
    "saving_throw": SavingThrowEffectItem,
    "armor": ArmorEffectItem,
    "weapon": WeaponEffectItem,
    "spell": SpellEffectItem,
}


class _EffectGroupsPayload(BaseModel):
    """
    Write-side base for a payload carrying a list of effect groups (each type at most once).

    Exposes each type's items under the legacy per-type attribute names
    (``skill_effects`` ...) that the validators and ``FeatureEffectsService``
    read; a type with no group yields ``_ABSENT``.
    """

    _ABSENT: ClassVar[list | None] = []

    def _groups(self) -> list:
        raise NotImplementedError

    def _items(self, effect_type: str) -> list | None:
        return next((group.items for group in self._groups() if group.effect_type == effect_type), self._ABSENT)

    @property
    def ability_effects(self) -> list | None:
        return self._items("ability")

    @property
    def skill_effects(self) -> list | None:
        return self._items("skill")

    @property
    def saving_throw_effects(self) -> list | None:
        return self._items("saving_throw")

    @property
    def armor_effects(self) -> list | None:
        return self._items("armor")

    @property
    def weapon_effects(self) -> list | None:
        return self._items("weapon")

    @property
    def spell_effects(self) -> list | None:
        return self._items("spell")


def _reject_repeated_types(groups: list) -> list:
    """Reject the same ``effect_type`` appearing twice in one bundle."""

    _reject_duplicates([group.effect_type for group in groups], "effect_type")
    return groups


class ChoiceOptionPayload(_EffectGroupsPayload):
    """
    One option of a choice group, carrying its effect bundle as ``effects``
    (the same ``EffectGroup`` list the read side returns).

    Only the ONE effect type its group's ``choice_type`` allows may carry
    items (see ``ChoiceGroupPayload``) — an option never mixes effect kinds.
    Carries no label of its own — what it grants is read straight off its
    effects (and rendered to text on read, see ``effects.rendering``).

    ``id``: see ``SkillEffectItem`` — present on a response only; a new option
    must not carry one. A bundle may not repeat an effect type, and an
    effect group may not repeat an effect.
    """

    model_config = ConfigDict(extra="forbid")

    id: EntityId | None = None
    sort_order: int = Field(0, ge=0, le=MAX_SORT_ORDER)
    effects: list[EffectGroup] = Field([], max_length=len(_ALL_OPTION_EFFECT_FIELDS))

    _validate_types = field_validator("effects")(_reject_repeated_types)

    def _groups(self) -> list:
        return self.effects

    @model_validator(mode="after")
    def validate_no_duplicate_effects(self):
        """Reject a repeated row id or a repeated effect inside one option."""

        _validate_effect_lists(self, _ALL_OPTION_EFFECT_FIELDS)
        return self


class ChoiceGroupPayload(BaseModel):
    """
    One "pick N of M" group of a feature.

    ``choice_type`` fixes what kind of effect this group's options carry —
    every option's ``effects`` may only hold the one effect type that choice
    type allows (e.g. ``SKILL`` → only ``skill``). One effect type per group,
    no mixed bundles.

    ``id``: see ``SkillEffectItem`` — present on a response only; a new group
    (and its options) must not carry one.
    """

    model_config = ConfigDict(extra="forbid")

    id: EntityId | None = None
    pick_count: int = Field(1, ge=1, le=MAX_PICK_COUNT)
    sort_order: int = Field(0, ge=0, le=MAX_SORT_ORDER)
    choice_type: ChoiceType
    options: list[ChoiceOptionPayload] = Field([], max_length=MAX_OPTIONS_PER_GROUP)
    # Groups no longer carry a label; old clients still send one, so it is accepted and dropped.
    label: str | None = Field(None, max_length=200, exclude=True)

    @model_validator(mode="after")
    def validate_unique_option_ids(self):
        """Reject the same option id appearing twice in one group."""

        _reject_duplicates([option.id for option in self.options if option.id is not None], "option id")
        return self

    @model_validator(mode="after")
    def validate_options_match_choice_type(self):
        """Reject an option carrying an effect list outside its group's declared ``choice_type``."""

        allowed_type = EFFECT_TYPE_BY_CHOICE_TYPE[self.choice_type]
        for index, option in enumerate(self.options):
            for group in option.effects:
                if group.effect_type != allowed_type and group.items:
                    raise ValueError(
                        f"Option {index} in a '{self.choice_type.value}' group may not carry "
                        f"'{group.effect_type}' effects — only '{allowed_type}' is allowed here."
                    )
        return self


class ChoiceOptionResponse(BaseModel):
    """A choice option with its id and bundle: only its non-empty effect groups (``FeatureChoiceOption.effects``)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sort_order: int = 0
    effects: list[EffectGroup] = []


class ChoiceGroupResponse(BaseModel):
    """A choice group with its DB id and resolved options."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    feature_id: int
    pick_count: int
    sort_order: int = 0
    choice_type: ChoiceType
    options: list[ChoiceOptionResponse] = []


class FeatureEffectsResponse(BaseModel):
    """Aggregated effect tree of a feature: its choice groups and its fixed effects."""

    feature_id: int
    choice_groups: list[ChoiceGroupResponse] = []
    static_groups: list[EffectGroup] = []


class FeatureEffectsUpdate(_EffectGroupsPayload):
    """
    Payload for adding fixed effects, as the same ``static_groups`` list
    ``GET /features/{id}/effects`` returns (also the body of an option's
    ``POST .../effects``). Every item becomes a new row. A fixed skill/spell
    effect needs a concrete ``skill_id``/``spell_id``; a type may appear once,
    and a group may not repeat an id or an effect.
    """

    model_config = ConfigDict(extra="forbid")

    _ABSENT: ClassVar[list | None] = None
    # Whether ``skill_id=None`` / ``spell_id=None`` ("any skill/spell") is accepted — only inside a choice option.
    _OPEN_ALLOWED: ClassVar[bool] = False

    static_groups: list[EffectGroup] = Field([], max_length=len(_ALL_OPTION_EFFECT_FIELDS))

    _validate_types = field_validator("static_groups")(_reject_repeated_types)

    def _groups(self) -> list:
        return self.static_groups

    @model_validator(mode="after")
    def validate_effects(self):
        """Reject duplicate ids/effects and fixed skill/spell effects with no concrete target."""

        _validate_effect_lists(self, _ALL_OPTION_EFFECT_FIELDS)

        if not self._OPEN_ALLOWED and any(effect.skill_id is None for effect in self.skill_effects or []):
            raise ValueError("A fixed skill_effects entry requires skill_id.")

        if not self._OPEN_ALLOWED and any(effect.spell_id is None for effect in self.spell_effects or []):
            raise ValueError("A fixed spell_effects entry requires spell_id.")

        return self


class OptionEffectsUpdate(FeatureEffectsUpdate):
    """
    Body of an option's ``POST .../options/{option_id}/effects``: the same
    ``static_groups`` list, except a skill/spell effect may be open
    (``skill_id``/``spell_id`` unset — "any skill/spell").
    """

    _OPEN_ALLOWED: ClassVar[bool] = True


class ChoiceGroupPatch(BaseModel):
    """PATCH payload for a choice group: only the fields sent change (``choice_type`` is fixed at creation)."""

    model_config = ConfigDict(extra="forbid")

    pick_count: int | None = Field(None, ge=1, le=MAX_PICK_COUNT)
    sort_order: int | None = Field(None, ge=0, le=MAX_SORT_ORDER)

    @model_validator(mode="after")
    def reject_explicit_null(self):
        """``null`` isn't a valid value for either column."""

        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("pick_count and sort_order cannot be null.")
        return self


class ChoiceOptionPatch(BaseModel):
    """PATCH payload for a choice option: its order. Its effects are edited via the option's ``/effects`` routes."""

    model_config = ConfigDict(extra="forbid")

    sort_order: int = Field(ge=0, le=MAX_SORT_ORDER)
