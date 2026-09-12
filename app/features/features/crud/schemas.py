"""Request/response schemas for the feature endpoints and nested parent feature payloads."""

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.constants import AbilityScore, FeatureSourceType
from app.features.features.effects.schemas import (
    AbilityEffectItem,
    ArmorEffectItem,
    ChoiceGroupResponse,
    SavingThrowEffectItem,
    SkillEffectItem,
    SpellEffectItem,
    WeaponEffectItem,
)

# Which FK field must be set (and which must be empty) for each source_type.
# SUBCLASS keys off subclass_id (not class_id — the old denorm approach).
# FEAT and OTHER require none of the FKs; a FEAT row carries the feat
# columns (min_level / prerequisite_*) instead.
_REQUIRED_FK_BY_SOURCE_TYPE: dict[FeatureSourceType, str | None] = {
    FeatureSourceType.CLASS: "class_id",
    FeatureSourceType.SUBCLASS: "subclass_id",
    FeatureSourceType.RACE: "race_id",
    FeatureSourceType.SUBRACE: "subrace_id",
    FeatureSourceType.BACKGROUND: "background_id",
    FeatureSourceType.FEAT: None,
    FeatureSourceType.OTHER: None,
}
_ALL_SOURCE_FKS = ("class_id", "subclass_id", "race_id", "subrace_id", "background_id")

# ``level`` is mandatory for class/subclass features and optional otherwise.
_LEVEL_REQUIRED_SOURCE_TYPES = (FeatureSourceType.CLASS, FeatureSourceType.SUBCLASS)

# Valid level range for level-gated features (class/subclass abilities).
_FEATURE_LEVEL_MIN = 1
_FEATURE_LEVEL_MAX = 20


def _validate_source_fk_consistency(source_type: FeatureSourceType, values: dict) -> None:
    """Enforce that exactly the FK matching ``source_type`` is set (and the others empty), plus the level rules."""

    required_fk = _REQUIRED_FK_BY_SOURCE_TYPE[source_type]

    for fk_name in _ALL_SOURCE_FKS:
        fk_value = values.get(fk_name)

        if fk_name == required_fk and fk_value is None:
            raise ValueError(f"source_type='{source_type.value}' requires '{fk_name}' to be set.")

        if fk_name != required_fk and fk_value is not None:
            raise ValueError(
                f"source_type='{source_type.value}' must not set '{fk_name}' (only '{required_fk}' applies)."
                if required_fk
                else f"source_type='{source_type.value}' must not set '{fk_name}'."
            )

    level = values.get("level")

    if source_type in _LEVEL_REQUIRED_SOURCE_TYPES:
        if level is None:
            raise ValueError(f"source_type='{source_type.value}' requires 'level' to be set.")

        if not (_FEATURE_LEVEL_MIN <= level <= _FEATURE_LEVEL_MAX):
            raise ValueError(
                f"'level' for CLASS/SUBCLASS features must be between {_FEATURE_LEVEL_MIN} and {_FEATURE_LEVEL_MAX}."
            )


def _validate_min_level(value: int | None) -> int | None:
    """Reject an out-of-range ``min_level`` when provided."""

    if value is not None and not (_FEATURE_LEVEL_MIN <= value <= _FEATURE_LEVEL_MAX):
        raise ValueError(f"min_level must be between {_FEATURE_LEVEL_MIN} and {_FEATURE_LEVEL_MAX}.")

    return value


class FeatPrerequisiteFields(BaseModel):
    """
    Feat-only prerequisite/level-gate fields (only meaningful for
    ``source_type=FEAT`` rows).

    Factored out so the dedicated ``/feats`` catalog schemas
    (``app/features/feats/crud/schemas.py``) can reuse this exact field set
    instead of redeclaring it — both write the same underlying ``Feature``
    columns.
    """

    prerequisite_ability: AbilityScore | None = None
    prerequisite_minimum_score: int | None = None
    prerequisite_description: str = ""
    min_level: int | None = None

    @field_validator("min_level")
    @classmethod
    def validate_min_level(cls, value: int | None) -> int | None:
        """Reject an out-of-range ``min_level`` when provided."""

        return _validate_min_level(value)


class FeatPrerequisiteFieldsUpdate(BaseModel):
    """Same fields as :class:`FeatPrerequisiteFields`, all optional for PATCH semantics."""

    prerequisite_ability: AbilityScore | None = None
    prerequisite_minimum_score: int | None = None
    prerequisite_description: str | None = None
    min_level: int | None = None

    @field_validator("min_level")
    @classmethod
    def validate_min_level(cls, value: int | None) -> int | None:
        """Reject an out-of-range ``min_level`` when provided."""

        return _validate_min_level(value)


class FeatureBase(FeatPrerequisiteFields):
    """Base feature fields, including the source_type/FK/level consistency rules."""

    model_config = ConfigDict(extra="forbid")

    name: str
    source_type: FeatureSourceType

    class_id: int | None = None
    subclass_id: int | None = None
    race_id: int | None = None
    subrace_id: int | None = None
    background_id: int | None = None

    level: int | None = None

    description: str = ""

    # ``min_level``/``prerequisite_*`` (inherited from ``FeatPrerequisiteFields``)
    # are only meaningful when source_type == FEAT. A standalone feat-like row
    # also carries no choice/effects data in this schema — the effect engine
    # (choice groups + fixed effects) is managed through the
    # ``/features/{id}/effects`` endpoints.


class FeatureCreate(FeatureBase):
    """
    Payload for ``POST /features`` — create a feature of ANY source type,
    including FEAT now.

    The parent FK is set directly for source-owned features; a standalone
    ``FEAT`` or ``OTHER`` feature needs no FK. Feat rows additionally carry
    ``min_level`` / ``prerequisite_*``.
    """

    @model_validator(mode="after")
    def validate_source_fk_consistency(self):
        """Enforce the source_type/FK/level consistency rules on write payloads."""

        _validate_source_fk_consistency(self.source_type, self.__dict__)
        return self


class FeatureResponse(FeatureBase):
    """Full feature representation returned by the API, with the complete effect tree."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ability_effects: list[AbilityEffectItem] = []
    choice_groups: list[ChoiceGroupResponse] = []
    skill_effects: list[SkillEffectItem] = []
    saving_throw_effects: list[SavingThrowEffectItem] = []
    armor_effects: list[ArmorEffectItem] = []
    weapon_effects: list[WeaponEffectItem] = []
    spell_effects: list[SpellEffectItem] = []
    # Server-rendered, read-only: plain ``Feature`` properties (see
    # ``app/models/features/feature_model.py`` and
    # ``app.features.features.effects.rendering``), picked up automatically
    # by ``model_validate`` off the eager-loaded effect tree — never
    # accepted on write (this schema is response-only).
    has_static_effects: bool = False
    has_choices: bool = False
    effects_summary: str = ""


class FeatureGetAllResponse(BaseModel):
    """Lightweight listing row: no description."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_type: FeatureSourceType
    class_id: int | None = None
    subclass_id: int | None = None
    race_id: int | None = None
    subrace_id: int | None = None
    background_id: int | None = None
    level: int | None = None
    ability_effects: list[AbilityEffectItem] = []
    has_static_effects: bool = False
    has_choices: bool = False
    effects_summary: str = ""


class NestedFeatureCreate(BaseModel):
    """
    A feature embedded in a parent create payload (race, subrace, class,
    background, subclass).

    The owning service injects ``source_type`` and the matching source FK,
    then validates the merged payload through ``FeatureCreate``.
    """

    name: str
    description: str = ""
    level: int | None = None


class NestedFeatureResponse(BaseModel):
    """Compact feature row for embedding inside a parent entity response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    level: int | None = None
    ability_effects: list[AbilityEffectItem] = []
    has_static_effects: bool = False
    has_choices: bool = False
    effects_summary: str = ""


class FeatureUpdate(FeatPrerequisiteFieldsUpdate):
    """
    All fields optional — PATCH semantics.

    ``source_type`` and its FK are immutable once a feature exists; only
    ``name``, ``level``, ``description`` are editable for source-owned
    features, plus the feat columns (``min_level``, ``prerequisite_*``,
    inherited from ``FeatPrerequisiteFieldsUpdate``) for FEAT rows. A
    CLASS/SUBCLASS feature's ``level`` can be changed but never cleared —
    the service enforces this against the existing ``source_type``.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    level: int | None = None
    description: str | None = None
