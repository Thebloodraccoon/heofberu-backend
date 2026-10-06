"""Request/response schemas for the subclass CRUD endpoints."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.features.classes.schema_utils import (
    DESCRIPTION_MAX_LENGTH,
    IMAGE_URL_MAX_LENGTH,
    NAME_MAX_LENGTH,
    null_guard,
    validate_image_url,
)
from app.features.features.crud.schemas import NestedFeatureResponse


class SubclassCreate(BaseModel):
    """Create payload for a subclass; its features are added afterwards through the central features catalog."""

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    class_id: int = Field(gt=0)
    description: str = Field("", max_length=DESCRIPTION_MAX_LENGTH)
    image_url: str | None = Field(None, max_length=IMAGE_URL_MAX_LENGTH)

    _image_url = field_validator("image_url")(validate_image_url)


class SubclassUpdate(BaseModel):
    """All fields optional (PATCH); neither accepts an explicit ``null``. Does not touch features."""

    name: str | None = Field(None, min_length=1, max_length=NAME_MAX_LENGTH)
    description: str | None = Field(None, max_length=DESCRIPTION_MAX_LENGTH)

    _no_nulls = null_guard()


class SubclassResponse(BaseModel):
    """
    Full subclass representation returned by the API (``GET``, ``POST`` and
    ``PATCH``): base fields plus the subclass's own SUBCLASS-source ``features``.
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
