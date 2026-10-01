"""Schemas for HP updates and rests."""

from typing import Literal

from pydantic import BaseModel, Field

from app.features.characters.schemas import HP_LIMIT


class HpUpdate(BaseModel):
    """
    Update HP either by a relative `delta` or by setting absolute
    `current_hp`/`temp_hp` — not both styles at once. Values are bounded
    in magnitude; the service clamps them to the character's valid range.
    """

    delta: int | None = Field(default=None, ge=-HP_LIMIT, le=HP_LIMIT)
    current_hp: int | None = Field(default=None, ge=-HP_LIMIT, le=HP_LIMIT)
    temp_hp: int | None = Field(default=None, ge=-HP_LIMIT, le=HP_LIMIT)


class RestRequest(BaseModel):
    """Rest request body: ``type`` must be ``"short"`` or ``"long"`` (rejected by ``Literal`` with a 422)."""

    type: Literal["short", "long"]
