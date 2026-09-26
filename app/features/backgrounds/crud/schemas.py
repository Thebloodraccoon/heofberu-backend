"""Request/response schemas for the background CRUD endpoints."""

from pydantic import BaseModel, ConfigDict

from app.features.backgrounds.skills.schemas import SkillResponse
from app.features.backgrounds.suggestions.schemas import SuggestionResponse
from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.shared.items.schemas import ChoiceGroupResponse, SourceItemResponse
from app.features.shared.tags.schemas import TagBrief


class BackgroundBase(BaseModel):
    """Base background fields shared by create, update, and response schemas."""

    name: str
    description: str = ""
    starting_gold: int = 0


class BackgroundCreate(BackgroundBase):
    """
    Create payload for a background: base fields only.

    ``granted_skills``/``suggestions``/``tags`` (like ``features``/``starting_items``)
    are deliberately not part of create — they're attached afterwards through
    their own PUT full-replace endpoints.
    """


class BackgroundUpdate(BaseModel):
    """
    All fields optional — only provided fields are updated (PATCH semantics).
    """

    name: str | None = None
    description: str | None = None
    starting_gold: int | None = None


class BackgroundResponse(BackgroundBase):
    """Full background representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    suggestions: list[SuggestionResponse] = []
    granted_skills: list[SkillResponse] = []
    features: list[NestedFeatureResponse] = []
    starting_items: list[SourceItemResponse] = []
    starting_choice_groups: list[ChoiceGroupResponse] = []
    tags: list[TagBrief] = []


class BackgroundGetAllResponse(BaseModel):
    """Lightweight listing row: id and name only, served via the column-select fast path."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
