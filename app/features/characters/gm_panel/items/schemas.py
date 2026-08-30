"""
Request schemas for GM-managed item stacks on a character.

The response shape (``CharacterItemResponse`` and its embedded item
record) lives in the top-level ``characters/schemas.py`` because it is
shared by the player-facing reads in ``crud/`` and by these writes.
"""

from pydantic import BaseModel, Field


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
