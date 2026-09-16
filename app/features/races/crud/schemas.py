"""Request/response schemas for the race CRUD endpoints (race identity; capability schemas live in their own folders)."""

from pydantic import BaseModel, ConfigDict

from app.constants import RaceSize
from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.races.ability_bonuses.schemas import AbilityBonusResponse
from app.features.races.skills.schemas import SkillResponse
from app.features.subraces.crud.schemas import SubraceGetAllResponse


class RaceBase(BaseModel):
    """Base race fields shared by create, update, and response schemas."""

    name: str
    size: RaceSize = RaceSize.MEDIUM
    speed: int = 30
    description: str = ""
    image_url: str | None = None


class RaceCreate(RaceBase):
    """
    Create payload for a race: base fields only.

    ``ability_bonuses``, ``granted_skills``, and ``features`` are
    deliberately not part of create — each is attached afterwards through
    its own capability endpoint (a lightweight create, mirroring backgrounds).
    """


class RaceUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    name: str | None = None
    size: RaceSize | None = None
    speed: int | None = None
    description: str | None = None
    image_url: str | None = None


class RaceResponse(RaceBase):
    """Full race representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ability_bonuses: list[AbilityBonusResponse] = []
    granted_skills: list[SkillResponse] = []
    features: list[NestedFeatureResponse] = []
    subraces: list[SubraceGetAllResponse] = []


class RaceGetAllResponse(BaseModel):
    """Lightweight listing row returned by the paginated ``GET /races`` endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    size: RaceSize
    image_url: str | None = None
