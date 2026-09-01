"""Request schemas for GM-managed item stacks on a character."""

from pydantic import BaseModel, Field


class CharacterItemAdd(BaseModel):
    """Add a stack of an item to a character's inventory (a character may own multiple stacks)."""

    item_id: int
    quantity: int = Field(default=1, ge=0)
    is_equipped: bool = False
    is_attuned: bool = False
    notes: str = ""


class CharacterItemUpdate(BaseModel):
    """Change a stack's quantity, equip/attunement state, or notes (``item_id`` itself is immutable)."""

    quantity: int | None = Field(default=None, ge=0)
    is_equipped: bool | None = None
    is_attuned: bool | None = None
    notes: str | None = None
