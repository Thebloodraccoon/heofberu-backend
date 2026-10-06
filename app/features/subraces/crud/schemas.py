"""Request/response schemas for the subrace CRUD endpoints."""

from pydantic import BaseModel, ConfigDict

from app.core.types import EntityId
from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.shared.catalog.schemas import (
    AbilityBonusResponse,
    CatalogName,
    Description,
    PartialUpdate,
    SubraceBrief,
)
from app.features.shared.tags.schemas import TagBrief


class SubraceCreate(BaseModel):
    """
    Create payload for a subrace: base fields only.

    ``ability_bonuses``, ``tags``, and ``features`` are deliberately not
    part of create: each is attached afterwards through its own
    capability endpoint (mirroring races). ``image_url`` is set only via
    ``PUT /subraces/{id}/image``.
    """

    name: CatalogName
    race_id: EntityId
    description: Description = ""


class SubraceUpdate(PartialUpdate):
    """All fields optional: only provided fields are updated (PATCH semantics); none accepts ``null``."""

    name: CatalogName | None = None
    description: Description | None = None


class SubraceResponse(BaseModel):
    """
    Full subrace representation returned by the API.

    Used by create, update, the capability PUTs and ``GET /subraces/{id}``;
    ``features`` are the subrace's own SUBRACE-source features.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    race_id: int
    name: str
    description: str
    image_url: str | None = None
    ability_bonuses: list[AbilityBonusResponse] = []
    features: list[NestedFeatureResponse] = []
    tags: list[TagBrief] = []


class SubraceGetAllResponse(SubraceBrief):
    """Lightweight subrace row returned by ``GET /subraces`` (also embedded in ``RaceResponse.subraces``)."""
