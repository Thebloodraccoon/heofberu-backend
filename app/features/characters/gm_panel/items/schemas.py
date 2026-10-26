"""Request schemas for GM-managed item stacks on a character."""

from pydantic import BaseModel, Field, field_validator

MAX_ITEM_QUANTITY = 1_000_000


class CharacterItemAdd(BaseModel):
    """Add a stack of an item to a character's inventory (a character may own multiple stacks)."""

    item_id: int = Field(gt=0)
    quantity: int = Field(default=1, ge=1, le=MAX_ITEM_QUANTITY)


# 5e: a creature can be attuned to no more than three magic items at a time.
MAX_ATTUNED_ITEMS = 3


class CharacterItemUpdate(BaseModel):
    """
    Change a stack's quantity or its equip/attunement state (``item_id`` itself is immutable). Only an item
    that ``requires_attunement`` can be attuned, at most ``MAX_ATTUNED_ITEMS`` at a time.
    """

    quantity: int | None = Field(default=None, ge=0, le=MAX_ITEM_QUANTITY)
    is_equipped: bool | None = None
    is_attuned: bool | None = None

    @field_validator("quantity", "is_equipped", "is_attuned")
    @classmethod
    def reject_explicit_null(cls, value):
        """Omit a field to leave it unchanged."""

        if value is None:
            raise ValueError("This field cannot be null; omit it to leave it unchanged.")
        return value
