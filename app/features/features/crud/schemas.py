"""Request/response schemas for the feature endpoints."""

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.constants import FeatureSourceType
from app.features.shared.features.schemas import _validate_source_fk_consistency


class FeatureBase(BaseModel):
    """Base feature fields, including the source_type/FK consistency rules."""

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
    nested ``features`` payload (race, subrace, class, background,
    subclass).
    """


class StandaloneFeatureCreate(FeatureBase):
    """
    Payload for ``POST /features/`` — standalone features only.

    ``source_type`` is pinned to ``OTHER`` so no source FK is involved.
    CLASS/SUBCLASS/RACE/SUBRACE/BACKGROUND features are owned by their
    parent record and must be supplied through that parent's create
    payload (``race.features``, ``background.features`` etc.); posting
    them directly here is rejected with a 422.
    """

    source_type: FeatureSourceType = FeatureSourceType.OTHER

    @field_validator("source_type")
    def validate_standalone_only(cls, value):
        if value != FeatureSourceType.OTHER:
            raise ValueError(
                "Only standalone (OTHER) features can be created through /features/; "
                "CLASS/SUBCLASS/RACE/SUBRACE/BACKGROUND features are created through their parent entities."
            )

        return value


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
    subrace_id: int | None = None
    background_id: int | None = None
    level: int | None = None
