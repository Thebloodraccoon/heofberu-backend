"""Schemas for items owned by a character."""

from pydantic import BaseModel, ConfigDict, Field


class CharacterItemAdd(BaseModel):
    """
    Add a stack of an item to a character's inventory.

    ``quantity`` defaults to 1 (0 is allowed). A character may own
    multiple stacks of the same item — each POST creates its own stack
    row.
    """

    item_id: int
    quantity: int = Field(default=1, ge=0)
    is_equipped: bool = False
    is_attuned: bool = False
    notes: str = ""


class CharacterItemUpdate(BaseModel):
    """
    Change an item stack's quantity, equip/attunement state, or notes.

    There's no way to change ``item_id`` itself — remove the stack and
    add a new one instead.
    """

    quantity: int | None = Field(default=None, ge=0)
    is_equipped: bool | None = None
    is_attuned: bool | None = None
    notes: str | None = None


class CharacterItemResponse(BaseModel):
    """Aggregates an owned item stack with its quantity and state flags."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
    item_id: int
    quantity: int
    is_equipped: bool
    is_attuned: bool
    notes: str = ""
