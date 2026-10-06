"""Feature effects capability: request/response schemas for the effect engine (Phase 3)."""

from collections.abc import Callable
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.constants import (
    EFFECT_TYPE_BY_CHOICE_TYPE,
    AbilityScore,
    ArmorProficiency,
    ChoiceType,
    WeaponProficiency,
)
from app.core.types import EntityId

VALID_NEW_CAP_MIN = 20
VALID_NEW_CAP_MAX = 30

MAX_EFFECTS_PER_LIST = 50
MAX_OPTIONS_PER_GROUP = 50
MAX_CHOICE_GROUPS = 20
MAX_PICK_COUNT = 50
MAX_SORT_ORDER = 10_000
MAX_ABILITY_AMOUNT = 30


# What makes two effects of the same type "the same effect" (and so a duplicate).
DUPLICATE_KEY_BY_EFFECT_FIELD: dict[str, Callable[[Any], Any]] = {
    "ability_effects": lambda effect: effect.ability,
    "skill_effects": lambda effect: effect.skill_id,
    "saving_throw_effects": lambda effect: effect.ability,
    "armor_effects": lambda effect: effect.armor_type,
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
    A fixed/option skill-proficiency effect: a concrete ``skill_id``.

    ``skill_id=None`` ("any skill", choice options only) can no longer be
    WRITTEN — ``ChoiceGroupPayload.validate_options_match_choice_type``
    rejects it on a SKILL-type choice group, since the system doesn't yet
    support resolving an open skill pick end to end. Reads may still show
    ``None`` on a pre-existing catalog row.

    ``id`` is the DB row id: present on a response, and the path's ``effect_id``
    for a point write — a new row's payload must not carry one (422).
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: EntityId | None = None
    skill_id: EntityId | None = None
    grants_expertise: bool = False


class SavingThrowEffectItem(BaseModel):
    """A fixed/option saving-throw-proficiency effect. ``id``: see ``SkillEffectItem``."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: EntityId | None = None
    ability: AbilityScore


class ArmorEffectItem(BaseModel):
    """A fixed/option armor-proficiency effect. ``id``: see ``SkillEffectItem``."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: EntityId | None = None
    armor_type: ArmorProficiency


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
    A fixed/option spell-grant effect: a concrete ``spell_id``.

    An open choice (``spell_id`` unset, letting the player pick any spell
    from the catalog) can no longer be WRITTEN — same restriction as
    ``SkillEffectItem``'s open skill, and for the same reason. Reads may
    still show ``None`` on a pre-existing catalog row.

    ``id``: see ``SkillEffectItem``.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: EntityId | None = None
    spell_id: EntityId | None = None


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

    @model_validator(mode="after")
    def validate_no_open_picks(self):
        """
        Reject a new/updated SKILL or SPELL option left "open" (``skill_id``/
        ``spell_id`` unset) — the system doesn't yet support resolving an
        open pick end to end, so authoring one is disallowed until it does.
        Pre-existing catalog rows with an open effect are untouched by this
        (only reachable by re-submitting the same option unchanged, which
        would fail here too — an open option must be given a concrete id to
        pass through an update).
        """

        for index, option in enumerate(self.options):
            if self.choice_type == ChoiceType.SKILL:
                for skill_effect in option.skill_effects or []:
                    if skill_effect.skill_id is None:
                        raise ValueError(
                            f"Option {index}: an open ('any skill') skill effect is not "
                            "supported — skill_id is required."
                        )
            elif self.choice_type == ChoiceType.SPELL:
                for spell_effect in option.spell_effects or []:
                    if spell_effect.spell_id is None:
                        raise ValueError(
                            f"Option {index}: an open ('any spell') spell effect is not "
                            "supported — spell_id is required."
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

    static_groups: list[EffectGroup] = Field([], max_length=len(_ALL_OPTION_EFFECT_FIELDS))

    _validate_types = field_validator("static_groups")(_reject_repeated_types)

    def _groups(self) -> list:
        return self.static_groups

    @model_validator(mode="after")
    def validate_effects(self):
        """Reject duplicate ids/effects and fixed skill/spell effects with no concrete target."""

        _validate_effect_lists(self, _ALL_OPTION_EFFECT_FIELDS)

        if any(effect.skill_id is None for effect in self.skill_effects or []):
            raise ValueError("A fixed skill_effects entry requires skill_id.")

        if any(effect.spell_id is None for effect in self.spell_effects or []):
            raise ValueError("A fixed spell_effects entry requires spell_id.")

        return self


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
