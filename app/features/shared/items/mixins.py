"""Reusable starting-equipment mixin shared by the class/background services."""

from typing import Any

from app.constants import FeatureSourceType
from app.features.shared.items.nested_service import NestedSourceItemService
from app.features.shared.items.schemas import SourceItemResponse, SourceItemsUpdate


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
