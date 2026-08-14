"""
Shared starting-equipment schemas for the cross-catalog nested flows.

Used by the class/background services, their per-source item endpoints,
and the ``shared.items`` mixins/nested service. The public ``Item*``
request/response schemas are owned by the ``items`` catalog
(``app.features.items.crud.schemas``).
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import ItemType


class SourceItemEntry(BaseModel):
    """One starting-equipment entry: a reference item plus a quantity."""

    item_id: int
    quantity: int = Field(default=1, ge=0)


def _validate_unique_item_ids(entries: list[SourceItemEntry]) -> list[SourceItemEntry]:
    item_ids = [entry.item_id for entry in entries]
    if len(item_ids) != len(set(item_ids)):
        raise ValueError("Duplicate item IDs are not allowed.")

    return entries


class SourceItemsUpdate(BaseModel):
    """Full replacement list of starting items for a class or background."""

    items: list[SourceItemEntry]

    @field_validator("items")
    def validate_unique_item_ids(cls, items):
        """Reject lists containing duplicate item IDs."""
        return _validate_unique_item_ids(items)


class ItemBriefResponse(BaseModel):
    """Compact item representation embedded in source-item listings."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    item_type: ItemType


class SourceItemResponse(BaseModel):
    """A starting-equipment entry as returned by ``GET /{source}/{id}/items``."""

    model_config = ConfigDict(from_attributes=True)

    item_id: int
    quantity: int
    item: ItemBriefResponse
