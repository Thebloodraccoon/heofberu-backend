"""Class choice-group service: per-source list and full replacement."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.features.classes.cache import CLASS_CACHE_NAMESPACES
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.schemas import ClassResponse
from app.features.shared.items.choice_group_service import ChoiceGroupService


class ClassChoiceGroupService(ChoiceGroupService):
    """
    Choice-group management for a class's starting equipment alternatives.

    Delegates to :class:`ChoiceGroupService` with CLASS source type and
    the class cache namespaces.
    """

    cache_namespaces = CLASS_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            db,
            repository=ClassRepository(db),
            response_schema=ClassResponse,
            source_type=FeatureSourceType.CLASS,
        )
