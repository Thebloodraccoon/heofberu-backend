"""Request/response schemas for the subrace CRUD endpoints."""

from pydantic import BaseModel, ConfigDict

from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.races.ability_bonuses.schemas import AbilityBonusResponse
from app.features.shared.tags.schemas import TagBrief


class SubraceBase(BaseModel):
    """Base subrace fields shared by create, update, and response schemas."""

    name: str
    race_id: int
    description: str = ""


class SubraceCreate(SubraceBase):
    """
    Create payload for a subrace (nested under a race): base fields only.

    ``ability_bonuses``, ``tags``, and ``features`` are deliberately not
    part of create — each is attached afterwards through its own
    capability endpoint (mirroring races). ``image_url`` is set only via
    ``PUT /subraces/{id}/image``.
    """


class SubraceUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics). ``image_url`` is set via its own image endpoint."""

    name: str | None = None
    description: str | None = None


class SubraceResponse(SubraceBase):
    """
    Full subrace representation returned by the API.

    Doubles as both the create/update response and the
    ``GET /subraces/{id}`` response: ``get_by_id`` folds the subrace's own
    SUBRACE-source ``features`` into it, while ``create``/``update`` return
    it with ``features`` at its empty default.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    race_id: int
    image_url: str | None = None
    ability_bonuses: list[AbilityBonusResponse] = []
    features: list[NestedFeatureResponse] = []
    tags: list[TagBrief] = []


class SubraceGetAllResponse(BaseModel):
    """Lightweight subrace row returned by ``GET /subraces`` and embedded in ``RaceResponse.subraces``."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    race_id: int
    name: str
    image_url: str | None = None
