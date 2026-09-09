"""Feature effects capability: request/response schemas for the effect engine (Phase 3)."""

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.constants import AbilityScore, ArmorProficiency, SpellLevel, SpellSchool, WeaponProficiency

# --- Single effect row payloads -------------------------------------------------

VALID_NEW_CAP_MIN = 20
VALID_NEW_CAP_MAX = 30


class AbilityEffectItem(BaseModel):
    """A fixed/option ability-score effect: ``amount`` added, optional ``new_cap`` raise."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore
    amount: int
    new_cap: int | None = None

    @field_validator("new_cap")
    @classmethod
    def validate_new_cap(cls, value):
        """Enforce the new_cap range (20–30) mirroring the legacy ASI validation."""
        if value is not None and not (VALID_NEW_CAP_MIN <= value <= VALID_NEW_CAP_MAX):
            raise ValueError(f"new_cap must be between {VALID_NEW_CAP_MIN} and {VALID_NEW_CAP_MAX}.")
        return value


class SkillEffectItem(BaseModel):
    """A fixed/option skill-proficiency effect. ``skill_id`` None = "any skill" (choice only)."""

    model_config = ConfigDict(from_attributes=True)

    skill_id: int | None = None
    grants_expertise: bool = False


class SavingThrowEffectItem(BaseModel):
    """A fixed/option saving-throw-proficiency effect."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore


class ArmorEffectItem(BaseModel):
    """A fixed/option armor-proficiency effect."""

    model_config = ConfigDict(from_attributes=True)

    armor_type: ArmorProficiency


class WeaponEffectItem(BaseModel):
    """A fixed/option weapon-proficiency effect: category OR concrete item — exactly one."""

    model_config = ConfigDict(from_attributes=True)

    weapon_category: WeaponProficiency | None = None
    item_id: int | None = None

    @model_validator(mode="after")
    def _guard_single_target(self):
        """Guard: exactly one of ``weapon_category`` / ``item_id`` must be set."""
        if (self.weapon_category is None) == (self.item_id is None):
            raise ValueError("Set exactly one of weapon_category or item_id.")
        return self


class SpellEffectItem(BaseModel):
    """A fixed/option spell-grant effect: a concrete spell OR an open filter."""

    model_config = ConfigDict(from_attributes=True)

    spell_id: int | None = None
    spell_school: SpellSchool | None = None
    spell_level_max: SpellLevel | None = None
    always_prepared: bool = True
    counts_against_known_limit: bool = False

    @model_validator(mode="after")
    def _guard_specific_or_filter(self):
        """Guard: a concrete ``spell_id`` excludes a school/level filter."""
        if self.spell_id is not None and (self.spell_school is not None or self.spell_level_max is not None):
            raise ValueError("Set spell_id or a school/level filter, not both.")
        return self


# --- Choice groups -------------------------------------------------------------


class ChoiceOptionPayload(BaseModel):
    """
    One option of a choice group, carrying its effect bundle.

    Choosing the option applies every effect below together (e.g. Resilient's
    "DEX" option: +1 DEX AND DEX saving-throw proficiency).
    """

    label: str = ""
    sort_order: int = 0
    ability_effects: list[AbilityEffectItem] = []
    skill_effects: list[SkillEffectItem] = []
    saving_throw_effects: list[SavingThrowEffectItem] = []
    armor_effects: list[ArmorEffectItem] = []
    weapon_effects: list[WeaponEffectItem] = []
    spell_effects: list[SpellEffectItem] = []


class ChoiceGroupPayload(BaseModel):
    """One "pick N of M" group of a feature."""

    pick_count: int = 1
    sort_order: int = 0
    label: str = ""
    options: list[ChoiceOptionPayload] = []


# --- Responses -----------------------------------------------------------------


class ChoiceOptionResponse(ChoiceOptionPayload):
    """A choice option with its DB id."""

    model_config = ConfigDict(from_attributes=True)

    id: int


class ChoiceGroupResponse(BaseModel):
    """A choice group with its DB id and resolved options."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    feature_id: int
    pick_count: int
    sort_order: int = 0
    label: str = ""
    options: list[ChoiceOptionResponse] = []


class FeatureEffectsResponse(BaseModel):
    """Aggregated effect tree of a feature: its choice groups and its fixed effects."""

    feature_id: int
    choice_groups: list[ChoiceGroupResponse] = []
    ability_effects: list[AbilityEffectItem] = []
    skill_effects: list[SkillEffectItem] = []
    saving_throw_effects: list[SavingThrowEffectItem] = []
    armor_effects: list[ArmorEffectItem] = []
    weapon_effects: list[WeaponEffectItem] = []
    spell_effects: list[SpellEffectItem] = []


class FeatureEffectsUpdate(BaseModel):
    """
    Full-replace payload for a feature's FIXED (automatic) effects.

    Every list replaces its table's rows for the feature (send ``[]`` to
    clear). Choice groups are managed separately via
    ``PUT /features/{id}/choice-groups``.
    """

    ability_effects: list[AbilityEffectItem] = []
    skill_effects: list[SkillEffectItem] = []
    saving_throw_effects: list[SavingThrowEffectItem] = []
    armor_effects: list[ArmorEffectItem] = []
    weapon_effects: list[WeaponEffectItem] = []
    spell_effects: list[SpellEffectItem] = []

    @field_validator("ability_effects")
    @classmethod
    def validate_unique_ability_effects(cls, value: list[AbilityEffectItem]) -> list[AbilityEffectItem]:
        """Reject duplicate abilities among a feature's fixed ability-score effects."""

        abilities = [item.ability for item in value]
        if len(abilities) != len(set(abilities)):
            duplicates = {a for a in abilities if abilities.count(a) > 1}
            raise ValueError(f"Duplicate ability score(s) in ability_effects: {sorted(duplicates)}")
        return value


class ChoiceGroupsUpdate(BaseModel):
    """Full-replace payload for a feature's choice groups (options included)."""

    choice_groups: list[ChoiceGroupPayload] = []
