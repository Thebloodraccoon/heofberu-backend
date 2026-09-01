"""Class starting-equipment service: per-source list and full replacement."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.features.classes.cache import CLASS_CACHE_NAMESPACES
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.schemas import ClassCreate, ClassResponse, ClassUpdate
from app.features.shared.items.mixins import ChoiceGroupManagerMixin, SourceItemManagerMixin
from app.features.shared.items.nested_service import NestedSourceItemService
from app.models.class_model import Class


class ClassItemsService(
    ChoiceGroupManagerMixin,
    SourceItemManagerMixin,
    BaseService[Class, ClassCreate, ClassUpdate, ClassResponse, None],
):
    """
    Everything about a class's starting equipment: flat items + choice groups.

    Item CRUD comes from :class:`SourceItemManagerMixin`,
    choice-group CRUD from :class:`ChoiceGroupManagerMixin`, and the
    generic CRUD machinery from :class:`BaseService`. Writes purge
    ``CLASS_CACHE_NAMESPACES`` via ``cache_namespaces``.
    """

    repository: ClassRepository

    _source_item_source_type = FeatureSourceType.CLASS

    cache_namespaces = CLASS_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize the service with its repository and the nested item service."""

        super().__init__(
            repository=ClassRepository(db),
            response_schema=ClassResponse,
        )
        self._items = NestedSourceItemService(db)
