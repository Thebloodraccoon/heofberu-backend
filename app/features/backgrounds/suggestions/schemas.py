"""Request/response schemas for the background suggestion endpoints."""

from pydantic import BaseModel, ConfigDict, Field

from app.constants import BackgroundSuggestionType


class SuggestionEntry(BaseModel):
    """One suggestion entry: which personality-card field it's for, plus its text."""

    suggestion_type: BackgroundSuggestionType
    text: str = Field(min_length=1)


class SuggestionsUpdate(BaseModel):
    """Full replacement list of a background's suggestions."""

    suggestions: list[SuggestionEntry]


class SuggestionResponse(BaseModel):
    """A suggestion entry as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    suggestion_type: BackgroundSuggestionType
    text: str
