"""Schemas for a character's backstory (served uncached, separately from the character)."""

from pydantic import BaseModel, ConfigDict, Field

from app.constants import BACKSTORY_MAX_LENGTH


class CharacterBackstoryUpdate(BaseModel):
    """Set or replace a backstory; ``content`` is capped at ``BACKSTORY_MAX_LENGTH`` by schema and DB constraint."""

    content: str = Field(default="", max_length=BACKSTORY_MAX_LENGTH)


class CharacterBackstoryResponse(BaseModel):
    """A character's backstory, fetched on demand and never cached."""

    model_config = ConfigDict(from_attributes=True)

    character_id: int
    content: str = ""
