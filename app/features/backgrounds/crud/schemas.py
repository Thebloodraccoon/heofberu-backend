"""Request/response schemas for the background CRUD endpoints."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.features.backgrounds.skills.schemas import SkillResponse, _validate_unique_skill_ids
from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.shared.items.schemas import ChoiceGroupResponse, SourceItemResponse


class BackgroundBase(BaseModel):
    """Base background fields shared by create, update, and response schemas."""

    name: str

    personality_traits_suggestions: str = ""
    ideals_suggestions: str = ""
    bonds_suggestions: str = ""
    flaws_suggestions: str = ""

    description: str = ""


class BackgroundCreate(BackgroundBase):
    """Create payload for a background."""

    granted_skills: list[int] | None = None

    @field_validator("granted_skills")
    def validate_unique_skill_ids(cls, value):
        """Reject lists containing duplicate skill IDs."""

        if value is None:
            return value

        return _validate_unique_skill_ids(value)


class BackgroundUpdate(BaseModel):
    """
    All fields optional — only provided fields are updated (PATCH semantics).

    Excludes ``granted_skills`` so that list keeps its own PUT full-replace
    endpoint.
    """

    name: str | None = None
    personality_traits_suggestions: str | None = None
    ideals_suggestions: str | None = None
    bonds_suggestions: str | None = None
    flaws_suggestions: str | None = None
    description: str | None = None


class BackgroundResponse(BackgroundBase):
    """Full background representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    granted_skills: list[SkillResponse] = []
    starting_items: list[SourceItemResponse] = []
    starting_choice_groups: list[ChoiceGroupResponse] = []


class BackgroundGetAllResponse(BaseModel):
    """Lightweight listing row: no suggestion text/description, but includes granted_skills."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    granted_skills: list[SkillResponse] = []


class BackgroundFullResponse(BackgroundResponse):
    """
    Everything about a background in one payload.

    Inherits the base fields, granted_skills, and starting_items from
    ``BackgroundResponse``, plus its own BACKGROUND-source ``features``.
    """

    features: list[NestedFeatureResponse] = []
