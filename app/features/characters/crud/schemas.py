"""Schemas for HP updates and rests."""

from typing import Literal

from pydantic import BaseModel


class HpUpdate(BaseModel):
    """
    Update a character's HP either by a relative delta or by setting
    absolute values. Provide either `delta` or one/both of
    `current_hp`/`temp_hp` — not both styles at once.
    """

    delta: int | None = None
    current_hp: int | None = None
    temp_hp: int | None = None


class RestRequest(BaseModel):
    """
    Rest request body: ``type`` must be ``"short"`` or ``"long"``.

    Validated by the ``Literal`` type, so any other value is rejected
    with a 422 at the schema layer — the old free-form ``str`` needed a
    manual check (and the ``InvalidRestTypeException``) in the service.
    """

    type: Literal["short", "long"]
