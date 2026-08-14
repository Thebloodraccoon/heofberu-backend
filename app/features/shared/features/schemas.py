"""
Shared feature schemas for the cross-catalog nested (parent-record) flows.

Only the nested payloads/responses and the source_type/FK consistency
helpers used by both the public ``features`` catalog and the parent
catalogs live here. The public ``Feature*`` request/response schemas are
owned by the ``features`` catalog (``app.features.features.crud.schemas``).
"""

from pydantic import BaseModel, ConfigDict

from app.constants import FeatureSourceType

# Which FK field must be set (and which must be empty) for each source_type.
# SUBCLASS now keys off subclass_id (not class_id — that was the old denorm approach).
# OTHER requires none of the FKs.
_REQUIRED_FK_BY_SOURCE_TYPE: dict[FeatureSourceType, str | None] = {
    FeatureSourceType.CLASS: "class_id",
    FeatureSourceType.SUBCLASS: "subclass_id",
    FeatureSourceType.RACE: "race_id",
    FeatureSourceType.SUBRACE: "subrace_id",
    FeatureSourceType.BACKGROUND: "background_id",
    FeatureSourceType.FEAT: "feat_id",
    FeatureSourceType.OTHER: None,
}
_ALL_SOURCE_FKS = ("class_id", "subclass_id", "race_id", "subrace_id", "background_id", "feat_id")

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
      - SUBRACE    -> subrace_id required, others must be None
      - BACKGROUND -> background_id required, others must be None
      - FEAT       -> feat_id required, others must be None
      - OTHER      -> none of the six may be set
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


class NestedFeatureCreate(BaseModel):
    """
    A feature embedded in a parent create payload (race, subrace, class,
    background, feat, subclass).

    The owning service injects ``source_type`` and the matching source FK,
    then validates the merged payload through ``FeatureCreate`` so the same
    consistency rules apply.
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


class FeatureUpdate(BaseModel):
    """
    All fields optional — PATCH semantics.

    ``source_type`` and its FK (``class_id``/``subclass_id``/``race_id``/
    ``subrace_id``/``background_id``/``feat_id``) are immutable once a feature
    exists — ownership never moves. Only ``name``, ``level`` and
    ``description`` are editable; setting ``level`` on a non-CLASS/
    SUBCLASS feature is still rejected by the service (level is only
    meaningful for class/subclass features).
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    level: int | None = None
    description: str | None = None
