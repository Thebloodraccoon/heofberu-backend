"""Request/response schemas for the feature endpoints."""

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.constants import FeatureSourceType

# Which FK field must be set (and which must be empty) for each source_type.
# SUBCLASS now keys off subclass_id (not class_id — that was the old denorm approach).
# OTHER requires none of the FKs.
_REQUIRED_FK_BY_SOURCE_TYPE: dict[FeatureSourceType, str | None] = {
    FeatureSourceType.CLASS: "class_id",
    FeatureSourceType.SUBCLASS: "subclass_id",
    FeatureSourceType.RACE: "race_id",
    FeatureSourceType.BACKGROUND: "background_id",
    FeatureSourceType.FEAT: "feat_id",
    FeatureSourceType.OTHER: None,
}
_ALL_SOURCE_FKS = ("class_id", "subclass_id", "race_id", "background_id", "feat_id")

# source_types for which the ``level`` field is meaningful.
_ALLOW_LEVEL = (
    FeatureSourceType.CLASS,
    FeatureSourceType.SUBCLASS,
    FeatureSourceType.OTHER,
)


def _validate_source_fk_consistency(source_type: FeatureSourceType, values: dict) -> None:
    """
    Enforce that exactly the FK matching ``source_type`` is set, and the
    others are left empty:
      - CLASS      -> class_id required, others must be None
      - SUBCLASS   -> subclass_id required, others must be None
      - RACE       -> race_id required, others must be None
      - BACKGROUND -> background_id required, others must be None
      - FEAT       -> feat_id required, others must be None
      - OTHER      -> none of the five may be set
    """

    required_fk = _REQUIRED_FK_BY_SOURCE_TYPE[source_type]

    for fk_name in _ALL_SOURCE_FKS:
        fk_value = values.get(fk_name)

        if fk_name == required_fk:
            if fk_value is None:
                raise ValueError(f"source_type='{source_type.value}' requires '{fk_name}' to be set.")
        else:
            if fk_value is not None:
                raise ValueError(
                    f"source_type='{source_type.value}' must not set '{fk_name}' (only '{required_fk}' applies)."
                    if required_fk
                    else f"source_type='{source_type.value}' must not set '{fk_name}'."
                )

    if source_type not in _ALLOW_LEVEL and values.get("level") is not None:
        raise ValueError("'level' is only meaningful when source_type is CLASS, SUBCLASS or OTHER.")


class FeatureBase(BaseModel):
    """Base feature fields, including the source_type/FK consistency rules."""

    name: str
    source_type: FeatureSourceType

    class_id: int | None = None
    subclass_id: int | None = None
    race_id: int | None = None
    background_id: int | None = None
    feat_id: int | None = None

    level: int | None = None

    description: str = ""
    is_homebrew: bool = False

    @model_validator(mode="after")
    def validate_source_fk_consistency(self):
        """Enforce that exactly the FK matching ``source_type`` is set."""
        _validate_source_fk_consistency(self.source_type, self.__dict__)
        return self


class FeatureCreate(FeatureBase):
    """
    Payload for creating a feature inside a parent entity (GM only).

    Direct creation through ``POST /features/`` uses
    :class:`StandaloneFeatureCreate` instead — non-OTHER features are
    owned by their parent record and are created through that parent's
    nested ``features`` payload (race, class, background, feat,
    subclass).
    """


class StandaloneFeatureCreate(FeatureBase):
    """
    Payload for ``POST /features/`` — standalone features only.

    ``source_type`` is pinned to ``OTHER`` so no source FK is involved.
    CLASS/SUBCLASS/RACE/BACKGROUND/FEAT features are owned by their
    parent record and must be supplied through that parent's create
    payload (``race.features``, ``background.features``, ``feat.features``
    etc.); posting them directly here is rejected with a 422.
    """

    source_type: FeatureSourceType = FeatureSourceType.OTHER

    @field_validator("source_type")
    def validate_standalone_only(cls, value):
        if value != FeatureSourceType.OTHER:
            raise ValueError(
                "Only standalone (OTHER) features can be created through /features/; "
                "CLASS/SUBCLASS/RACE/BACKGROUND/FEAT features are created through their parent entities."
            )

        return value


class NestedFeatureCreate(BaseModel):
    """
    A feature embedded in a parent create payload (race, class, background,
    feat, subclass).

    The owning service injects ``source_type`` and the matching source FK,
    then validates the merged payload through ``FeatureCreate`` so the same
    consistency rules apply.
    """

    name: str
    description: str = ""
    is_homebrew: bool = False
    level: int | None = None


class NestedFeatureResponse(BaseModel):
    """Compact feature row for embedding inside a parent entity response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    level: int | None = None
    is_homebrew: bool


class FeatureUpdate(BaseModel):
    """
    All fields optional — PATCH semantics.

    ``source_type`` and its FK (``class_id``/``subclass_id``/``race_id``/
    ``background_id``/``feat_id``) are immutable once a feature exists —
    ownership never moves. Only ``name``, ``level``, ``description`` and
    ``is_homebrew`` are editable; setting ``level`` on a non-CLASS/
    SUBCLASS feature is still rejected by the service (level is only
    meaningful for class/subclass features).
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    level: int | None = None
    description: str | None = None
    is_homebrew: bool | None = None


class FeatureResponse(FeatureBase):
    """Full feature representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by_id: int | None = None


class FeatureGetAllResponse(BaseModel):
    """Lightweight listing row: no description."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_type: FeatureSourceType
    class_id: int | None = None
    subclass_id: int | None = None
    race_id: int | None = None
    background_id: int | None = None
    feat_id: int | None = None
    level: int | None = None
    is_homebrew: bool
