"""Request schema for the GM max-HP write."""

from pydantic import BaseModel, Field


class MaxHpUpdate(BaseModel):
    """Set a character's maximum HP directly (GM-only); ``current_hp`` is clamped down to it when exceeding."""

    max_hp: int = Field(ge=0)
