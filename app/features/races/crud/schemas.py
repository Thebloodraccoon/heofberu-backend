"""Request/response schemas for the race CRUD endpoints (race identity; capability schemas live in their own folders)."""

from pydantic import BaseModel, ConfigDict

from app.constants import RaceSize
from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.races.skills.schemas import SkillResponse
from app.features.shared.catalog.schemas import (
    AbilityBonusResponse,
    CatalogName,
    Description,
    PartialUpdate,
    Speed,
    SubraceBrief,
)
from app.features.shared.tags.schemas import TagBrief


class RaceCreate(BaseModel):
    """
    Create payload for a race: base fields only.

    ``ability_bonuses``, ``granted_skills``, ``tags``, and ``features`` are
    deliberately not part of create — each is attached afterwards through
    its own capability endpoint (a lightweight create, mirroring backgrounds).
    ``image_url`` is set only via ``PUT /races/{id}/image``.
    """

    name: CatalogName
    size: RaceSize = RaceSize.MEDIUM
    speed: Speed = 30
    description: Description = ""


class RaceUpdate(PartialUpdate):
    """All fields optional — only provided fields are updated (PATCH semantics); none accepts ``null``."""

    name: CatalogName | None = None
    size: RaceSize | None = None
    speed: Speed | None = None
    description: Description | None = None


class RaceResponse(BaseModel):
    """Full race representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    size: RaceSize
    speed: int
    description: str
    image_url: str | None = None
    ability_bonuses: list[AbilityBonusResponse] = []
    granted_skills: list[SkillResponse] = []
    features: list[NestedFeatureResponse] = []
    subraces: list[SubraceBrief] = []
    tags: list[TagBrief] = []


class RaceGetAllResponse(BaseModel):
    """Lightweight listing row returned by the paginated ``GET /races`` endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    size: RaceSize
    image_url: str | None = None
