"""Response schema for a character's owned item stacks."""

from pydantic import BaseModel, ConfigDict

from app.features.items.crud.schemas import ItemResponse


class CharacterItemResponse(BaseModel):
    """
    Aggregates an owned item stack with its quantity/state flags and the
    full item record so the sheet renders without a follow-up call.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
    item_id: int
    quantity: int
    item: ItemResponse
