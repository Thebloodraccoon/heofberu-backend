"""Class starting-equipment service: per-source list and full replacement."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.features.classes.cache import CLASS_CACHE_NAMESPACES
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.schemas import ClassCreate, ClassResponse, ClassUpdate
from app.features.shared.items.mixins import SourceItemManagerMixin
from app.features.shared.items.nested_service import NestedSourceItemService
from app.models.class_model import Class


class ClassItemsService(
    SourceItemManagerMixin,
    BaseService[Class, ClassCreate, ClassUpdate, ClassResponse, None],
):
    """
    Everything about a class's starting equipment.

    ``list_items``/``set_items`` come from :class:`SourceItemManagerMixin`,
    which delegates the writes to the shared :class:`NestedSourceItemService`
    engine; the generic CRUD machinery (``_get_or_404``/``_get_response``/
    ``_invalidate_cache``) comes from :class:`BaseService`. Any write
    purges the ``classes``, ``nested_features`` and ``nested_items``
    namespaces via ``cache_namespaces``.
    """

    repository: ClassRepository

    _source_item_source_type = FeatureSourceType.CLASS

    cache_namespaces = CLASS_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=ClassRepository(db),
            response_schema=ClassResponse,
        )
        self._items = NestedSourceItemService(db)
