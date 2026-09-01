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

    Features are managed centrally through the features catalog. The
    cached ``list_features`` list lives under the ``class_features``
    namespace, which central feature writes invalidate.
    """

    repository: ClassRepository

    cache_namespaces = ("class_features",)

    def __init__(self, db: AsyncSession):
        """Initialize the service with its repository and the central feature catalog."""

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
