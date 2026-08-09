"""Request/response schemas for the background endpoints."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.features.features.schemas import NestedFeatureResponse, NestedFeatureCreate


class BackgroundBase(BaseModel):
    """Base background fields shared by create, update, and response schemas."""

    name: str

    personality_traits_suggestions: str = ""
    ideals_suggestions: str = ""
    bonds_suggestions: str = ""
    flaws_suggestions: str = ""

    description: str = ""
    is_homebrew: bool = False


def _validate_unique_skill_ids(skill_ids: list[int]) -> list[int]:
    if len(skill_ids) != len(set(skill_ids)):
        raise ValueError("Duplicate skill IDs are not allowed.")
    return skill_ids


class BackgroundCreate(BackgroundBase):
    """
    Create payload for a background.

    ``granted_skills`` is optional — a background can be created without
    it (matching prior behavior) or with it supplied up front, avoiding
    an extra PUT round-trip. When provided, semantics are "full replace
    from empty", same as the dedicated PUT endpoint.
    """

    granted_skills: list[int] | None = None
    features: list[NestedFeatureCreate] | None = None

    @field_validator("granted_skills")
    def validate_unique_skill_ids(cls, value):
        """Reject lists containing duplicate skill IDs."""
        if value is None:
            return value
        return _validate_unique_skill_ids(value)


class BackgroundUpdate(BaseModel):
    """
    All fields optional — only provided fields are updated (PATCH semantics).

    Deliberately does NOT include granted_skills: that keeps its own PUT
    endpoint with explicit full-replace semantics, since PATCH's "only
    touch what's set" doesn't map cleanly onto "replace the whole list".
    """

    name: str | None = None
    personality_traits_suggestions: str | None = None
    ideals_suggestions: str | None = None
    bonds_suggestions: str | None = None
    flaws_suggestions: str | None = None
    description: str | None = None
    is_homebrew: bool | None = None


class SkillsUpdate(BaseModel):
    """Full replacement list of skill IDs granted by a background."""

    skill_ids: list[int]

    @field_validator("skill_ids")
    def validate_unique_skill_ids(cls, skill_ids):
        """Reject lists containing duplicate skill IDs."""
        return _validate_unique_skill_ids(skill_ids)


class SkillResponse(BaseModel):
    """Brief skill representation embedded in background responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    name: str
    description: str


class BackgroundResponse(BackgroundBase):
    """Full background representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by_id: int | None = None
    granted_skills: list[SkillResponse] = []
    features: list[NestedFeatureResponse] = []


class BackgroundBriefResponse(BaseModel):
    """
    Lightweight listing row: no suggestion text/description, but includes
    granted_skills so dropdown/listing UI can show them without a
    follow-up call to `GET /backgrounds/{background_id}`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_homebrew: bool
    granted_skills: list[SkillResponse] = []
