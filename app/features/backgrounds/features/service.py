"""Background feature service: read-only, cached listing for BACKGROUND-source features."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.core.cache import use_cache
from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.backgrounds.crud.schemas import BackgroundCreate, BackgroundResponse, BackgroundUpdate
from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.features.crud.service import FeatureCrudService
from app.models import Background

class BackgroundFeatureService(
    BaseService[Background, BackgroundCreate, BackgroundUpdate, BackgroundResponse, None],
):
    """
    Read-only service for a background's BACKGROUND-source features.

    Features are managed centrally through the features catalog; this
    service only provides the cached ``list_features`` read.
    """

    repository: BackgroundRepository

    cache_namespaces = ("background_features",)

    def __init__(self, db: AsyncSession):
        """Compose the central ``FeatureCrudService`` for the cached list."""

        super().__init__(
            repository=BackgroundRepository(db),
            response_schema=BackgroundResponse,
        )
        self._features = FeatureCrudService(db)

    @use_cache()
    async def list_features(self, source_id: int) -> list[NestedFeatureResponse]:
        """Return every BACKGROUND-source feature of the background (cached)."""

        await self._get_or_404(source_id)
        return await self._features.list_for_source(FeatureSourceType.BACKGROUND, source_id)
