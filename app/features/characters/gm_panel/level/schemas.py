"""Request/response schemas for the GM max-level write."""

from pydantic import BaseModel, Field

from app.constants import CHARACTER_MAX_LEVEL


class MaxLevelUpdate(BaseModel):
    """
    Raise a character's maximum allowed level (GM-only).

    The value must be strictly greater than the currently stored maximum
    and can never exceed :data:`app.constants.CHARACTER_MAX_LEVEL` (20).
    Lowering the cap is not allowed.
    """

    max_level: int = Field(ge=1, le=CHARACTER_MAX_LEVEL)


class CharacterMaxLevelResponse(BaseModel):
    """The character's current level and the GM-set maximum it may reach."""

    character_id: int
    current_level: int
    max_level: int
