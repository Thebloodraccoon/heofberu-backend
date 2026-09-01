"""Shared starting-equipment schemas for cross-catalog nested flows."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import ItemType


class SourceItemEntry(BaseModel):
    """One starting-equipment entry: a reference item plus a quantity."""

    item_id: int
    quantity: int = Field(default=1, ge=0)


def _validate_unique_item_ids(entries: list[SourceItemEntry]) -> list[SourceItemEntry]:
    """Raise ``ValueError`` on duplicate item IDs."""

    item_ids = [entry.item_id for entry in entries]
    if len(item_ids) != len(set(item_ids)):
        raise ValueError("Duplicate item IDs are not allowed.")

    return entries


class SourceItemsUpdate(BaseModel):
    """Full replacement list of starting items."""

    items: list[SourceItemEntry]

    @field_validator("items")
    def validate_unique_item_ids(cls, items):
        """Reject duplicate item IDs in the starting-items list."""

        return _validate_unique_item_ids(items)


class ItemBriefResponse(BaseModel):
    """Compact item representation embedded in source-item listings."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    item_type: ItemType


class SourceItemResponse(BaseModel):
    """A starting-equipment entry as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    item_id: int
    quantity: int
    item: ItemBriefResponse


class ChoiceOptionEntry(BaseModel):
    """One option inside a choice group: a reference item plus a quantity."""

    item_id: int
    quantity: int = Field(default=1, ge=1)


class ChoiceGroupEntry(BaseModel):
    """A choice group: a pick count, ordered options, and optional sort order."""

    pick_count: int = Field(default=1, ge=1)
    sort_order: int = 0
    options: list[ChoiceOptionEntry] = Field(min_length=1)

    @field_validator("options")
    def validate_unique_item_ids(cls, options: list[ChoiceOptionEntry], info):
        """Reject duplicate item IDs and pick_count exceeding option count."""

        item_ids = [o.item_id for o in options]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("Duplicate item IDs within a choice group are not allowed.")

        pick_count = info.data.get("pick_count")
        if pick_count is not None and pick_count > len(options):
            raise ValueError("pick_count cannot exceed the number of options in the group.")
        return options


class ChoiceGroupsUpdate(BaseModel):
    """Full replacement list of choice groups."""

    choice_groups: list[ChoiceGroupEntry]


class ChoiceOptionResponse(BaseModel):
    """One option inside a choice group as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    quantity: int
    sort_order: int
    item: ItemBriefResponse


class ChoiceGroupResponse(BaseModel):
    """A choice group as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    pick_count: int
    sort_order: int
    options: list[ChoiceOptionResponse] = []


class ChoiceGroupsResponse(BaseModel):
    """The full list of choice groups for a source."""

    source_type: str
    source_id: int
    choice_groups: list[ChoiceGroupResponse] = []
