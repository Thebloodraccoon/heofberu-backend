"""Background starting-equipment service: per-source list and full replacement."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.features.backgrounds.cache import BACKGROUND_CACHE_NAMESPACES
from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.backgrounds.crud.schemas import BackgroundCreate, BackgroundResponse, BackgroundUpdate
from app.features.shared.items.mixins import SourceItemManagerMixin
from app.features.shared.items.nested_service import NestedSourceItemService
from app.models.background_model import Background


class BackgroundItemsService(
    SourceItemManagerMixin,
    BaseService[Background, BackgroundCreate, BackgroundUpdate, BackgroundResponse, None],
):
    """
    Everything about a background's starting equipment.

    ``list_items``/``set_items`` come from :class:`SourceItemManagerMixin`,
    which delegates the writes to the shared :class:`NestedSourceItemService`
    engine; the generic CRUD machinery (``_get_or_404``/``_get_response``/
    ``_invalidate_cache``) comes from :class:`BaseService`. Any write
    purges the ``backgrounds``, ``nested_features`` and ``nested_items``
    namespaces via ``cache_namespaces``.
    """

    repository: BackgroundRepository

    _source_item_source_type = FeatureSourceType.BACKGROUND

    cache_namespaces = BACKGROUND_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=BackgroundRepository(db),
            response_schema=BackgroundResponse,
        )
        self._items = NestedSourceItemService(db)
