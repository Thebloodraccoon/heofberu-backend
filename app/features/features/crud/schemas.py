"""Request/response schemas for the feature endpoints and nested parent feature payloads."""

from pydantic import BaseModel, ConfigDict, model_validator

from app.constants import FeatureSourceType
from app.features.features.ability_increases.schemas import AbilityIncreaseItem

# Which FK field must be set (and which must be empty) for each source_type.
# SUBCLASS keys off subclass_id (not class_id — the old denorm approach).
# OTHER requires none of the FKs; FEAT is no longer a valid source
# (a feat is de facto its own feature).
_REQUIRED_FK_BY_SOURCE_TYPE: dict[FeatureSourceType, str | None] = {
    FeatureSourceType.CLASS: "class_id",
    FeatureSourceType.SUBCLASS: "subclass_id",
    FeatureSourceType.RACE: "race_id",
    FeatureSourceType.SUBRACE: "subrace_id",
    FeatureSourceType.BACKGROUND: "background_id",
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

class FeatureBase(BaseModel):
    """Base feature fields, including the source_type/FK/level consistency rules."""

    # Stale/unknown keys (e.g. the removed FEAT source's feat_id) are rejected with 422,
    # never silently dropped.
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
    Payload for ``POST /features`` — create a feature of ANY source type.

    The parent FK is set directly for source-owned features; a standalone
    ``OTHER`` feature needs no FK.
    """

    @model_validator(mode="after")
    def validate_source_fk_consistency(self):
        """Enforce the source_type/FK/level consistency rules on write payloads."""

        _validate_source_fk_consistency(self.source_type, self.__dict__)
        return self

class FeatureResponse(FeatureBase):
    """Full feature representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ability_increases: list[AbilityIncreaseItem] = []

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
    ability_increases: list[AbilityIncreaseItem] = []

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
    ability_increases: list[AbilityIncreaseItem] = []

class FeatureUpdate(BaseModel):
    """
    All fields optional — PATCH semantics.

    ``source_type`` and its FK are immutable once a feature exists; only
    ``name``, ``level`` and ``description`` are editable. A CLASS/SUBCLASS
    feature's ``level`` can be changed but never cleared — the service
    enforces this against the existing ``source_type``.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    level: int | None = None
    description: str | None = None
