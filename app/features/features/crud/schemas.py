"""Request/response schemas for the feature endpoints and nested parent feature payloads."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.constants import AbilityScore, FeatureSourceType
from app.features.features.effects.schemas import ChoiceGroupResponse, EffectGroup

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

# Columns that only make sense on a FEAT-source row.
_FEAT_ONLY_FIELDS = ("min_level", "prerequisite_ability", "prerequisite_minimum_score", "prerequisite_description")

_NAME_MAX_LENGTH = 200
_TEXT_MAX_LENGTH = 20_000


def _validate_source_fk_consistency(source_type: FeatureSourceType, values: dict) -> None:
    """Enforce that exactly the FK matching ``source_type`` is set, plus the level and feat-column rules."""

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

    if source_type in _LEVEL_REQUIRED_SOURCE_TYPES and level is None:
        raise ValueError(f"source_type='{source_type.value}' requires 'level' to be set.")

    if level is not None and not (_FEATURE_LEVEL_MIN <= level <= _FEATURE_LEVEL_MAX):
        raise ValueError(f"'level' must be between {_FEATURE_LEVEL_MIN} and {_FEATURE_LEVEL_MAX}.")

    if source_type == FeatureSourceType.FEAT:
        if level is not None:
            raise ValueError("FEAT features do not use 'level' — set 'min_level' instead.")
    else:
        feat_fields = [name for name in _FEAT_ONLY_FIELDS if values.get(name) not in (None, "")]
        if feat_fields:
            raise ValueError(
                f"{', '.join(feat_fields)} {'is' if len(feat_fields) == 1 else 'are'} only valid for FEAT features."
            )

    _validate_prerequisite_pair(values.get("prerequisite_ability"), values.get("prerequisite_minimum_score"))


def _validate_prerequisite_pair(ability, minimum_score) -> None:
    """``prerequisite_ability`` and ``prerequisite_minimum_score`` are set together or not at all."""

    if (ability is None) != (minimum_score is None):
        raise ValueError("prerequisite_ability and prerequisite_minimum_score must be set together.")


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


class FeatureCreate(FeatureBase):
    """
    Payload for ``POST /features`` — create a feature of ANY source type,
    including FEAT now.

    The parent FK is set directly for source-owned features; a standalone
    ``FEAT`` or ``OTHER`` feature needs no FK. Feat rows additionally carry
    ``min_level`` / ``prerequisite_*``; those columns are rejected on every
    other source type, the same rule ``PATCH`` applies.
    """

    name: str = Field(min_length=1, max_length=_NAME_MAX_LENGTH)
    description: str = Field("", max_length=_TEXT_MAX_LENGTH)
    prerequisite_minimum_score: int | None = Field(None, ge=1, le=30)
    prerequisite_description: str = Field("", max_length=_TEXT_MAX_LENGTH)

    @model_validator(mode="after")
    def validate_source_fk_consistency(self):
        """Enforce the source_type/FK/level consistency rules on write payloads."""

        _validate_source_fk_consistency(self.source_type, self.__dict__)
        return self


class FeatureResponse(FeatureBase):
    """Full feature representation returned by the API, with the complete effect tree."""

    model_config = ConfigDict(from_attributes=True)

    id: int

    choice_groups: list[ChoiceGroupResponse] = []
    static_groups: list[EffectGroup] = []

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
    has_static_effects: bool = False
    has_choices: bool = False


class NestedFeatureCreate(BaseModel):
    """
    A feature embedded in a parent create payload (race, subrace, class,
    background, subclass).

    The owning service injects ``source_type`` and the matching source FK,
    then validates the merged payload through ``FeatureCreate``.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=_NAME_MAX_LENGTH)
    description: str = Field("", max_length=_TEXT_MAX_LENGTH)
    level: int | None = Field(None, ge=_FEATURE_LEVEL_MIN, le=_FEATURE_LEVEL_MAX)


class NestedFeatureResponse(BaseModel):
    """Feature row for embedding inside a parent entity response, with the complete effect tree."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    level: int | None = None

    choice_groups: list[ChoiceGroupResponse] = []
    static_groups: list[EffectGroup] = []

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

    name: str | None = Field(None, min_length=1, max_length=_NAME_MAX_LENGTH)
    level: int | None = None
    description: str | None = Field(None, max_length=_TEXT_MAX_LENGTH)
    prerequisite_minimum_score: int | None = Field(None, ge=1, le=30)
    prerequisite_description: str | None = Field(None, max_length=_TEXT_MAX_LENGTH)
