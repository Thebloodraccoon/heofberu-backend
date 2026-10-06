"""Class starting-equipment service: per-source list and full replacement."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.features.classes.cache import CLASS_ITEMS_CACHE_NAMESPACES
from app.features.classes.service_base import ClassScopedService
from app.features.shared.items.mixins import ChoiceGroupManagerMixin, SourceItemManagerMixin
from app.features.shared.items.nested_service import NestedSourceItemService


class ClassItemsService(ChoiceGroupManagerMixin, SourceItemManagerMixin, ClassScopedService):
    """
    A class's starting equipment: flat items plus choice groups.

    Item CRUD comes from :class:`SourceItemManagerMixin`, choice-group CRUD from
    :class:`ChoiceGroupManagerMixin`. Writes also purge the shared ``nested_items`` listings.
    """

    _source_item_source_type = FeatureSourceType.CLASS

    cache_namespaces = CLASS_ITEMS_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize the service with the nested item service."""

        super().__init__(db)
        self._items = NestedSourceItemService(db)
