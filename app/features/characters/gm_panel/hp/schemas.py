"""Request schema for the GM max-HP write."""

from pydantic import BaseModel, Field


class MaxHpUpdate(BaseModel):
    """
    Set a character's maximum HP directly (GM-only).

    ``max_hp`` is not PATCHable through the plain character update —
    only a GM may change it. ``current_hp`` is clamped down to the new
    maximum by the service when it exceeds it.
    """

    max_hp: int = Field(ge=0)
