"""Shared starting-equipment mixins for list/full-replace operations."""

from typing import Any

from app.constants import FeatureSourceType
from app.features.shared.items.nested_service import NestedSourceItemService
from app.features.shared.items.schemas import (
    ChoiceGroupsResponse,
    ChoiceGroupsUpdate,
    SourceItemResponse,
    SourceItemsUpdate,
)


class SourceItemManagerMixin:
    """List/full-replace starting equipment attached to a source record."""

    _items: NestedSourceItemService
    _source_item_source_type: FeatureSourceType

    async def list_items(self, source_id: int) -> list[SourceItemResponse]:
        """Return cached starting items for ``source_id``."""

        await self._get_or_404(source_id)
        return await self._items.list_for_source(self._source_item_source_type, source_id)

    async def set_items(self, source_id: int, data: SourceItemsUpdate) -> Any:
        """Fully replace starting items for ``source_id`` and return the source response."""

        await self._get_or_404(source_id)
        await self._items.set_items_for_source(self._source_item_source_type, source_id, data.items)
        await self._invalidate_cache()

        return await self._get_response(source_id)


class ChoiceGroupManagerMixin:
    """List/full-replace choice groups (class starting equipment alternatives)."""

    _items: NestedSourceItemService
    _source_item_source_type: FeatureSourceType

    async def list_choice_groups(self, source_id: int) -> ChoiceGroupsResponse:
        """Return choice groups for ``source_id``."""

        await self._get_or_404(source_id)
        return await self._items.list_choice_groups_for_source(self._source_item_source_type, source_id)

    async def set_choice_groups(self, source_id: int, data: ChoiceGroupsUpdate) -> ChoiceGroupsResponse:
        """Fully replace choice groups for ``source_id`` and return the updated list."""

        await self._get_or_404(source_id)
        result = await self._items.set_choice_groups_for_source(
            self._source_item_source_type, source_id, data.choice_groups, commit=True
        )
        await self._invalidate_cache()

        return result
