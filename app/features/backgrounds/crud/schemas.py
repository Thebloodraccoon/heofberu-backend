"""Request/response schemas for the background CRUD endpoints."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.features.backgrounds.skills.schemas import SkillResponse
from app.features.backgrounds.suggestions.schemas import SuggestionResponse
from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.shared.items.schemas import ChoiceGroupResponse, SourceItemResponse
from app.features.shared.tags.schemas import TagBrief

# Input bounds follow the column sizes; responses stay unconstrained so legacy rows always serialize.
BackgroundName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
StartingGold = Annotated[int, Field(ge=0, le=1_000_000_000)]


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

    name: BackgroundName
    starting_gold: StartingGold = 0


class BackgroundUpdate(BaseModel):
    """
    All fields optional — only provided fields are updated (PATCH semantics).

    An explicit ``null`` is rejected: every field maps to a NOT NULL column.
    """

    name: BackgroundName | None = None
    description: str | None = None
    starting_gold: StartingGold | None = None

    @field_validator("name", "description", "starting_gold")
    @classmethod
    def reject_explicit_null(cls, value):
        """Omit a field to leave it unchanged; ``null`` is not a valid value."""

        if value is None:
            raise ValueError("This field cannot be null; omit it to leave it unchanged.")

        return value


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
