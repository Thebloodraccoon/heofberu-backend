"""Request/response schemas for the tag dictionary endpoints."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalize_name(name: str) -> str:
    """Trim, collapse inner whitespace and lowercase; reject a blank name."""

    normalized = " ".join(name.split()).lower()
    if not normalized:
        raise ValueError("Tag name must not be blank.")

    return normalized


class TagBase(BaseModel):
    """Base tag fields shared by create and response schemas."""

    name: str = Field(max_length=100)


class TagCreate(TagBase):
    """Payload for creating a tag (GM only). The name is trimmed and lowercased."""

    @field_validator("name")
    def normalize_name(cls, name):
        """Trim, collapse whitespace and lowercase; reject a blank name."""

        return _normalize_name(name)


class TagUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    name: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    def normalize_name(cls, name):
        """Trim, collapse whitespace and lowercase; reject a blank or explicit-null name."""

        if name is None:
            raise ValueError("Tag name must not be blank.")

        return _normalize_name(name)


class TagResponse(TagBase):
    """Full tag representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int


class TagGetAllResponse(TagResponse):
    """Listing/autocomplete row: the tag plus how many records (races, subraces, backgrounds, articles) carry it."""

    usage_count: int = 0
