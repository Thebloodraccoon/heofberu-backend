"""Feature effects capability: request/response schemas for the effect engine (Phase 3)."""

from collections.abc import Callable
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.constants import AbilityScore, ArmorProficiency, ChoiceType, WeaponProficiency
from app.core.types import EntityId

# Which of a ``ChoiceOptionPayload``'s six effect-list fields a given
# ``ChoiceType`` allows non-empty. Every other field must be empty — see
# ``ChoiceGroupPayload.validate_options_match_choice_type``.
_ALLOWED_EFFECT_FIELD_BY_CHOICE_TYPE: dict[ChoiceType, str] = {
    ChoiceType.SKILL: "skill_effects",
    ChoiceType.SPELL: "spell_effects",
    ChoiceType.ABILITY_SCORE: "ability_effects",
    ChoiceType.SAVING_THROW: "saving_throw_effects",
    ChoiceType.ARMOR: "armor_effects",
    ChoiceType.WEAPON: "weapon_effects",
}
_ALL_OPTION_EFFECT_FIELDS = (
    "ability_effects",
    "skill_effects",
    "saving_throw_effects",
    "armor_effects",
    "weapon_effects",
    "spell_effects",
)

VALID_NEW_CAP_MIN = 20
VALID_NEW_CAP_MAX = 30

MAX_EFFECTS_PER_LIST = 50
MAX_OPTIONS_PER_GROUP = 50
MAX_CHOICE_GROUPS = 20
MAX_PICK_COUNT = 50
MAX_SORT_ORDER = 10_000
MAX_ABILITY_AMOUNT = 30


# What makes two effects of the same type "the same effect" (and so a duplicate).
_DUPLICATE_KEY_BY_EFFECT_FIELD: dict[str, Callable[[Any], Any]] = {
    "ability_effects": lambda effect: effect.ability,
    "skill_effects": lambda effect: effect.skill_id,
    "saving_throw_effects": lambda effect: effect.ability,
    "armor_effects": lambda effect: effect.armor_type,
    "weapon_effects": lambda effect: (effect.weapon_category, effect.item_id),
    "spell_effects": lambda effect: effect.spell_id,
}


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
        key = _DUPLICATE_KEY_BY_EFFECT_FIELD[field_name]
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

    ``id`` is the DB row id — absent (or omitted) on a write payload means
    "create"; set it to an existing row's id to update that row in place
    instead of replacing it (see ``FeatureEffectsService`` — writes diff by
    id rather than deleting and recreating every row).
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
    """A fixed/option weapon-proficiency effect: category OR concrete item — exactly one. ``id``: see ``SkillEffectItem``."""

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


class AbilityStaticEffectGroup(BaseModel):
    """A feature's fixed ability-score effects, grouped under ``effect_type='ability'``."""

    model_config = ConfigDict(from_attributes=True)

    effect_type: Literal["ability"] = "ability"
    items: list[AbilityEffectItem] = []


class SkillStaticEffectGroup(BaseModel):
    """A feature's fixed skill-proficiency effects, grouped under ``effect_type='skill'``."""

    model_config = ConfigDict(from_attributes=True)

    effect_type: Literal["skill"] = "skill"
    items: list[SkillEffectItem] = []


class SavingThrowStaticEffectGroup(BaseModel):
    """A feature's fixed saving-throw-proficiency effects, grouped under ``effect_type='saving_throw'``."""

    model_config = ConfigDict(from_attributes=True)

    effect_type: Literal["saving_throw"] = "saving_throw"
    items: list[SavingThrowEffectItem] = []


class ArmorStaticEffectGroup(BaseModel):
    """A feature's fixed armor-proficiency effects, grouped under ``effect_type='armor'``."""

    model_config = ConfigDict(from_attributes=True)

    effect_type: Literal["armor"] = "armor"
    items: list[ArmorEffectItem] = []


class WeaponStaticEffectGroup(BaseModel):
    """A feature's fixed weapon-proficiency effects, grouped under ``effect_type='weapon'``."""

    model_config = ConfigDict(from_attributes=True)

    effect_type: Literal["weapon"] = "weapon"
    items: list[WeaponEffectItem] = []


class SpellStaticEffectGroup(BaseModel):
    """A feature's fixed spell-grant effects, grouped under ``effect_type='spell'``."""

    model_config = ConfigDict(from_attributes=True)

    effect_type: Literal["spell"] = "spell"
    items: list[SpellEffectItem] = []


# One entry per non-empty fixed-effect relationship a ``Feature`` carries —
# built by ``Feature.static_groups`` (see ``app.models.features.feature_model``)
# and consumed by ``FeatureResponse``/``NestedFeatureResponse`` in place of
# six separate flat effect lists. ``effect_type`` discriminates which of the
# six typed groups a given entry is.
StaticEffectGroup = Annotated[
    AbilityStaticEffectGroup
    | SkillStaticEffectGroup
    | SavingThrowStaticEffectGroup
    | ArmorStaticEffectGroup
    | WeaponStaticEffectGroup
    | SpellStaticEffectGroup,
    Field(discriminator="effect_type"),
]


class ChoiceOptionPayload(BaseModel):
    """
    One option of a choice group, carrying its effect bundle.

    Only the ONE effect-list field its group's ``choice_type`` allows may be
    non-empty (see ``ChoiceGroupPayload``) — an option never mixes effect
    kinds. Carries no label of its own — what it grants is read straight off
    its effects (and rendered to text on read, see ``effects.rendering``),
    so authoring an option never risks a hand-typed name drifting from what
    it materializes.

    ``id``: see ``SkillEffectItem`` — omit to create a new option, set to an
    existing option's id to update it in place. Dropping an option a
    character has already picked from the payload clears that pick (it
    reverts to pending). An effect list may not repeat an id or an effect.
    """

    model_config = ConfigDict(extra="forbid")

    id: EntityId | None = None
    sort_order: int = Field(0, ge=0, le=MAX_SORT_ORDER)
    ability_effects: list[AbilityEffectItem] = Field([], max_length=MAX_EFFECTS_PER_LIST)
    skill_effects: list[SkillEffectItem] = Field([], max_length=MAX_EFFECTS_PER_LIST)
    saving_throw_effects: list[SavingThrowEffectItem] = Field([], max_length=MAX_EFFECTS_PER_LIST)
    armor_effects: list[ArmorEffectItem] = Field([], max_length=MAX_EFFECTS_PER_LIST)
    weapon_effects: list[WeaponEffectItem] = Field([], max_length=MAX_EFFECTS_PER_LIST)
    spell_effects: list[SpellEffectItem] = Field([], max_length=MAX_EFFECTS_PER_LIST)

    @model_validator(mode="after")
    def validate_no_duplicate_effects(self):
        """Reject a repeated row id or a repeated effect inside one option."""

        _validate_effect_lists(self, _ALL_OPTION_EFFECT_FIELDS)
        return self


class ChoiceGroupPayload(BaseModel):
    """
    One "pick N of M" group of a feature.

    ``choice_type`` fixes what kind of effect this group's options carry —
    every option may only populate the one effect-list field that type
    allows (e.g. ``SKILL`` → only ``skill_effects``); every other field must
    be empty. One effect type per group, no mixed bundles.

    ``id``: see ``SkillEffectItem`` — omit to create a new group, set to an
    existing group's id to update it (and diff its ``options``) in place.
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

        allowed_field = _ALLOWED_EFFECT_FIELD_BY_CHOICE_TYPE[self.choice_type]
        for index, option in enumerate(self.options):
            for field_name in _ALL_OPTION_EFFECT_FIELDS:
                if field_name == allowed_field:
                    continue
                if getattr(option, field_name):
                    raise ValueError(
                        f"Option {index} in a '{self.choice_type.value}' group may not set "
                        f"'{field_name}' — only '{allowed_field}' is allowed here."
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
                for effect in option.skill_effects:
                    if effect.skill_id is None:
                        raise ValueError(
                            f"Option {index}: an open ('any skill') skill_effects entry is not "
                            "supported — skill_id is required."
                        )
            elif self.choice_type == ChoiceType.SPELL:
                for effect in option.spell_effects:
                    if effect.spell_id is None:
                        raise ValueError(
                            f"Option {index}: an open ('any spell') spell_effects entry is not "
                            "supported — spell_id is required."
                        )
        return self


class ChoiceOptionResponse(BaseModel):
    """A choice option with its DB id and effect bundle (read side: no write-time validation)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sort_order: int = 0
    ability_effects: list[AbilityEffectItem] = []
    skill_effects: list[SkillEffectItem] = []
    saving_throw_effects: list[SavingThrowEffectItem] = []
    armor_effects: list[ArmorEffectItem] = []
    weapon_effects: list[WeaponEffectItem] = []
    spell_effects: list[SpellEffectItem] = []


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
    static_groups: list[StaticEffectGroup] = []


class FeatureEffectsUpdate(BaseModel):
    """
    Diff-update payload for a feature's FIXED (automatic) effects.

    Each effect type that is **present** becomes the complete set for that
    type, diffed by id rather than deleted and recreated wholesale: an item
    with an existing row's ``id`` updates it in place, one with no ``id``
    inserts a new row, and an existing row absent from the list is deleted
    (send ``[]`` to clear a type entirely). An effect type that is **omitted**
    (or ``null``) is left untouched. Choice groups are managed separately via
    ``PUT /features/{id}/choice-groups``. A fixed skill/spell effect needs a
    concrete ``skill_id``/``spell_id``; a list may not repeat an id or an effect.
    """

    model_config = ConfigDict(extra="forbid")

    ability_effects: list[AbilityEffectItem] | None = Field(None, max_length=MAX_EFFECTS_PER_LIST)
    skill_effects: list[SkillEffectItem] | None = Field(None, max_length=MAX_EFFECTS_PER_LIST)
    saving_throw_effects: list[SavingThrowEffectItem] | None = Field(None, max_length=MAX_EFFECTS_PER_LIST)
    armor_effects: list[ArmorEffectItem] | None = Field(None, max_length=MAX_EFFECTS_PER_LIST)
    weapon_effects: list[WeaponEffectItem] | None = Field(None, max_length=MAX_EFFECTS_PER_LIST)
    spell_effects: list[SpellEffectItem] | None = Field(None, max_length=MAX_EFFECTS_PER_LIST)

    @model_validator(mode="after")
    def validate_effects(self):
        """Reject duplicate ids/effects and fixed skill/spell effects with no concrete target."""

        _validate_effect_lists(self, _ALL_OPTION_EFFECT_FIELDS)

        if any(effect.skill_id is None for effect in self.skill_effects or []):
            raise ValueError("A fixed skill_effects entry requires skill_id.")

        if any(effect.spell_id is None for effect in self.spell_effects or []):
            raise ValueError("A fixed spell_effects entry requires spell_id.")

        return self


class ChoiceGroupsUpdate(BaseModel):
    """Full-replace payload for a feature's choice groups (options included); ``choice_groups`` is required."""

    model_config = ConfigDict(extra="forbid")

    choice_groups: list[ChoiceGroupPayload] = Field(max_length=MAX_CHOICE_GROUPS)

    @model_validator(mode="after")
    def validate_unique_group_ids(self):
        """Reject the same group id appearing twice."""

        _reject_duplicates([group.id for group in self.choice_groups if group.id is not None], "group id")
        return self

    @model_validator(mode="after")
    def validate_single_ability_choice_group(self):
        """
        Reject a second choice group of type ``ABILITY_SCORE``.

        ``feat_ability_score_effects`` (and every ASI grant-answering path
        built on it) assumes "at most one" choice group carries the ASI
        alternatives — a feature offering, say, "+2 STR or +2 DEX" is one
        group with two options, not two separate groups.
        """

        ability_groups = [group for group in self.choice_groups if group.choice_type == ChoiceType.ABILITY_SCORE]
        if len(ability_groups) > 1:
            raise ValueError("A feature may have at most one choice group of type ABILITY_SCORE.")
        return self
