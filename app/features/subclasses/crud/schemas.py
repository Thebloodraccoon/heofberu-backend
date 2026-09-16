"""Request/response schemas for the subclass CRUD endpoints."""

from pydantic import BaseModel, ConfigDict

from app.features.features.crud.schemas import NestedFeatureResponse


class SubclassCreate(BaseModel):
    """Create payload for a subclass. ``features`` are created in the same transaction with ``source_type=SUBCLASS`` and ``subclass_id`` set automatically."""

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
    """
    Full subclass representation returned by the API.

    Doubles as both the create/update response and the
    ``GET /subclasses/{id}`` response: ``get_by_id`` folds the subclass's
    own SUBCLASS-source ``features`` into it, while ``create``/``update``
    return it with ``features`` at its empty default.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    class_id: int
    name: str
    description: str
    image_url: str | None = None
    features: list[NestedFeatureResponse] = []


class SubclassGetAllResponse(BaseModel):
    """
    Lightweight subclass row returned by ``GET /subclasses`` and embedded
    in both ``ClassResponse.subclasses`` and ``ClassGetAllResponse.subclasses``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    class_id: int
    name: str
    image_url: str | None = None
