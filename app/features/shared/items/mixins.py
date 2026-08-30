"""Reusable starting-equipment mixin shared by the class/background services."""

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
    """
    Service mixin: list/full-replace the starting equipment attached to a
    source record.

    Used by the class/background services. Concrete services set
    ``_source_item_source_type`` to their ``FeatureSourceType`` and
    instantiate ``self._items = NestedSourceItemService(db)``.
    """

    _items: NestedSourceItemService
    _source_item_source_type: FeatureSourceType

    async def list_items(self, source_id: int) -> list[SourceItemResponse]:
        """Return every starting-equipment entry owned by ``source_id``."""

        await self._get_or_404(source_id)
        return await self._items.list_for_source(self._source_item_source_type, source_id)

    async def set_items(self, source_id: int, data: SourceItemsUpdate) -> Any:
        """Fully replace the starting equipment owned by ``source_id``."""

        await self._get_or_404(source_id)
        await self._items.set_items_for_source(self._source_item_source_type, source_id, data.items)
        await self._invalidate_cache()

        return await self._get_response(source_id)


class ChoiceGroupManagerMixin:
    """
    Service mixin: list/full-replace the choice groups attached to a source
    record (class starting equipment alternatives).

    Used by the class item service alongside :class:`SourceItemManagerMixin`.
    Concrete services set ``_source_item_source_type`` to their
    ``FeatureSourceType`` and instantiate ``self._items = NestedSourceItemService(db)``.
    """

    _items: NestedSourceItemService
    _source_item_source_type: FeatureSourceType

    async def list_choice_groups(self, source_id: int) -> ChoiceGroupsResponse:
        """Return every choice group (with nested options) for ``source_id``."""

        await self._get_or_404(source_id)
        return await self._items.list_choice_groups_for_source(self._source_item_source_type, source_id)

    async def set_choice_groups(self, source_id: int, data: ChoiceGroupsUpdate) -> ChoiceGroupsResponse:
        """Fully replace the choice groups owned by ``source_id``."""

        await self._get_or_404(source_id)
        result = await self._items.set_choice_groups_for_source(
            self._source_item_source_type, source_id, data.choice_groups, commit=True
        )
        await self._invalidate_cache()

        return result
