"""Request/response schemas for the subclass CRUD endpoints."""

from pydantic import BaseModel, ConfigDict

from app.features.features.crud.schemas import NestedFeatureResponse


class SubclassCreate(BaseModel):
    """
    Create payload for a subclass.

    ``features`` are created in the same transaction as the subclass itself
    with ``source_type=SUBCLASS`` and ``subclass_id`` set automatically.
    """

    name: str
    class_id: int
    description: str = ""
    image_url: str | None = None


class SubclassUpdate(BaseModel):
    """All fields optional — PATCH semantics. Does not touch features."""

    name: str | None = None
    description: str | None = None
    image_url: str | None = None


class SubclassResponse(BaseModel):
    """Full subclass representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    class_id: int
    name: str
    description: str
    image_url: str | None = None


class SubclassBriefResponse(BaseModel):
    """Lightweight subclass row for listings."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    class_id: int
    name: str
    image_url: str | None = None


class SubclassListResponse(BaseModel):
    """Minimal subclass reference embedded in ``ClassGetAllResponse.subclasses``."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    image_url: str | None = None


class SubclassFullResponse(SubclassResponse):
    """A subclass plus its own SUBCLASS-source features, for the aggregate class view."""

    features: list[NestedFeatureResponse] = []
