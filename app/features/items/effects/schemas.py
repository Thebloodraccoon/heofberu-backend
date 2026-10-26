"""Response schema for an item's effects."""

from pydantic import BaseModel

from app.features.features.effects.schemas import EffectGroup


class ItemEffectsResponse(BaseModel):
    """The speed/AC effects an item gives while equipped, as non-empty effect groups."""

    item_id: int
    effects: list[EffectGroup] = []
