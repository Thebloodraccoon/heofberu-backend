"""Class feature service: read-only, cached listing for CLASS-source features."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.cache import use_cache
from app.features.classes.service_base import ClassScopedService
from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.features.crud.service import FeatureCrudService


class ClassFeatureService(ClassScopedService):
    """
    Read-only service for a class's CLASS-source features.

    Features are managed centrally through the features catalog; central feature
    writes invalidate the cached list kept under ``class_features``.
    """

    cache_namespaces = ("class_features",)

    def __init__(self, db: AsyncSession):
        """Initialize the service with the central feature catalog."""

        super().__init__(db)
        self._features = FeatureCrudService(db)

    @use_cache()
    async def list_features(self, source_id: int) -> list[NestedFeatureResponse]:
        """Return every CLASS-source feature of the class (cached)."""

        await self._exists_or_404(source_id)
        return await self._features.list_for_source(FeatureSourceType.CLASS, source_id)
