"""Request/response schemas for the background suggestion endpoints."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import BackgroundSuggestionType

SUGGESTION_TEXT_MAX_LENGTH = 2000


class SuggestionEntry(BaseModel):
    """One suggestion entry: which personality-card field it's for, plus its text."""

    suggestion_type: BackgroundSuggestionType
    text: str = Field(min_length=1, max_length=SUGGESTION_TEXT_MAX_LENGTH)


class SuggestionCreate(SuggestionEntry):
    """Payload to add one suggestion to a background."""


class SuggestionUpdate(BaseModel):
    """Payload to edit one existing suggestion. Only set fields are changed."""

    suggestion_type: BackgroundSuggestionType | None = None
    text: str | None = Field(default=None, min_length=1, max_length=SUGGESTION_TEXT_MAX_LENGTH)

    @field_validator("suggestion_type", "text")
    @classmethod
    def reject_explicit_null(cls, value):
        """Both columns are NOT NULL: omit the field instead of sending ``null``."""

        if value is None:
            raise ValueError("This field cannot be null; omit it to leave it unchanged.")

        return value


class SuggestionResponse(BaseModel):
    """A suggestion entry as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    suggestion_type: BackgroundSuggestionType
    text: str
