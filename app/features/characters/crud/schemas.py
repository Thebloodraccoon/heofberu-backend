"""Schemas for HP updates and rests."""

from typing import Literal

from pydantic import BaseModel


class HpUpdate(BaseModel):
    """
    Update HP either by a relative `delta` or by setting absolute
    `current_hp`/`temp_hp` — not both styles at once.
    """

    delta: int | None = None
    current_hp: int | None = None
    temp_hp: int | None = None


class RestRequest(BaseModel):
    """Rest request body: ``type`` must be ``"short"`` or ``"long"`` (rejected by ``Literal`` with a 422)."""

    type: Literal["short", "long"]
