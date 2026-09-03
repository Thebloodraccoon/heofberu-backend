"""Background starting-equipment service: per-source list and full replacement."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.features.backgrounds.cache import BACKGROUND_CACHE_NAMESPACES
from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.backgrounds.crud.schemas import BackgroundCreate, BackgroundResponse, BackgroundUpdate
from app.features.shared.items.mixins import SourceItemManagerMixin
from app.features.shared.items.nested_service import NestedSourceItemService
from app.models import Background


class BackgroundItemsService(
    SourceItemManagerMixin,
    BaseService[Background, BackgroundCreate, BackgroundUpdate, BackgroundResponse, None],
):
    """
    Background starting-equipment service: per-source list and full replacement.

    ``list_items``/``set_items`` come from :class:`SourceItemManagerMixin`;
    generic CRUD machinery comes from :class:`BaseService`. Backgrounds grant
    flat items with no choice-group mechanic (that exists for classes only).
    """

    repository: BackgroundRepository

    _source_item_source_type = FeatureSourceType.BACKGROUND

    cache_namespaces = BACKGROUND_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Compose the nested source-item service."""

        super().__init__(
            repository=BackgroundRepository(db),
            response_schema=BackgroundResponse,
        )
        self._items = NestedSourceItemService(db)
