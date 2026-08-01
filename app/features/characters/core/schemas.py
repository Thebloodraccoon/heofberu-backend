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
    type: str  # "short" or "long"
