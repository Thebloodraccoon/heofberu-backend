"""Class feature service: read-only, cached listing for CLASS-source features."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.core.cache import use_cache
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.schemas import ClassCreate, ClassResponse, ClassUpdate
from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.features.crud.service import FeatureCrudService
from app.models.class_model import Class


class ClassFeatureService(
    BaseService[Class, ClassCreate, ClassUpdate, ClassResponse, None],
):
    """
    Read-only service for a class's CLASS-source features.

    Write endpoints (add/update/remove) have been removed from the
    per-catalog surface — features are managed centrally through the
    features catalog. This service only provides the cached
    ``list_features`` for the ``GET /classes/features?class_id=...`` read
    endpoint: the list is cached under the dedicated ``class_features``
    namespace, which the central feature writes invalidate (only for this
    class's list) via ``FeatureCrudService``.
    """

    repository: ClassRepository

    cache_namespaces = ("class_features",)

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=ClassRepository(db),
            response_schema=ClassResponse,
        )
        self._features = FeatureCrudService(db)

    @use_cache()
    async def list_features(self, source_id: int) -> list[NestedFeatureResponse]:
        """Return every CLASS-source feature of the class (cached)."""

        await self._get_or_404(source_id)
        return await self._features.list_for_source(FeatureSourceType.CLASS, source_id)
