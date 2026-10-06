"""Background starting-equipment service: flat items and "pick N of M" choice groups."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.features.backgrounds.cache import BACKGROUND_ITEMS_CACHE_NAMESPACES
from app.features.backgrounds.capability import BackgroundCapabilityService
from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.shared.items.mixins import ChoiceGroupManagerMixin, SourceItemManagerMixin
from app.features.shared.items.nested_service import NestedSourceItemService


class BackgroundItemsService(ChoiceGroupManagerMixin, SourceItemManagerMixin, BackgroundCapabilityService):
    """
    Background starting equipment: flat items plus choice groups.

    ``list_items``/``set_items`` come from :class:`SourceItemManagerMixin`,
    ``list_choice_groups``/``set_choice_groups`` from
    :class:`ChoiceGroupManagerMixin`. Character creation resolves the
    background's choice groups the same way it does a class's.
    """

    _source_item_source_type = FeatureSourceType.BACKGROUND

    cache_namespaces = BACKGROUND_ITEMS_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Compose the nested source-item service."""

        super().__init__(BackgroundRepository(db))
        self._items = NestedSourceItemService(db)
