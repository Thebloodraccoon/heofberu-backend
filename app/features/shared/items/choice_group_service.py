"""Choice-group management service shared by class/background services."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.features.shared.items.mixins import ChoiceGroupManagerMixin
from app.features.shared.items.nested_service import NestedSourceItemService


class ChoiceGroupService(
    ChoiceGroupManagerMixin,
    BaseService,
):
    """Generic choice-group read/write for any source type."""

    _source_item_source_type: FeatureSourceType

    cache_namespaces = ("nested_items",)

    def __init__(self, db: AsyncSession, *, repository, response_schema, source_type: FeatureSourceType):
        """Initialise the choice-group service with the given repository and source type."""

        super().__init__(repository=repository, response_schema=response_schema)
        self._items = NestedSourceItemService(db)
        self._source_item_source_type = source_type
