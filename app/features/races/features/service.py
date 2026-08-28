"""Race feature service: read-only, cached listing for RACE-source features."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.core.cache import use_cache
from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.features.crud.service import FeatureCrudService
from app.features.races.crud.repository import RaceRepository
from app.features.races.schemas import RaceCreate, RaceResponse, RaceUpdate
from app.models.race_model import Race


class RaceFeatureService(
    BaseService[Race, RaceCreate, RaceUpdate, RaceResponse, None],
):
    """
    Read-only service for a race's RACE-source features.

    Write endpoints have been removed — features are managed centrally
    through the features catalog. This service only provides the cached
    ``list_features`` for the ``GET /races/features?race_id=...`` read
    endpoint: the list is cached under the dedicated ``race_features``
    namespace, which the central feature writes invalidate (only for this
    race's list) via ``FeatureCrudService``.
    """

    repository: RaceRepository

    cache_namespaces = ("race_features",)

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=RaceRepository(db),
            response_schema=RaceResponse,
        )
        self._features = FeatureCrudService(db)

    @use_cache()
    async def list_features(self, source_id: int) -> list[NestedFeatureResponse]:
        """Return every RACE-source feature of the race (cached)."""

        await self._get_or_404(source_id)
        return await self._features.list_for_source(FeatureSourceType.RACE, source_id)
