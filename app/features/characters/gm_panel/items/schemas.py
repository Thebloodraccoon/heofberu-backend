"""Request schemas for GM-managed item stacks on a character."""

from pydantic import BaseModel, Field

MAX_ITEM_QUANTITY = 1_000_000


class CharacterItemAdd(BaseModel):
    """Add a stack of an item to a character's inventory (a character may own multiple stacks)."""

    item_id: int = Field(gt=0)
    quantity: int = Field(default=1, ge=1, le=MAX_ITEM_QUANTITY)


class CharacterItemUpdate(BaseModel):
    """Change a stack's quantity (``item_id`` itself is immutable)."""

    quantity: int | None = Field(default=None, ge=0, le=MAX_ITEM_QUANTITY)
