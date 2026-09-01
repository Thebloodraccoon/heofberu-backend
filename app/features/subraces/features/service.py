"""Subrace feature service: read-only, cached listing for SUBRACE-source features."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.core.cache import use_cache
from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.features.crud.service import FeatureCrudService
from app.features.subraces.crud.repository import SubraceRepository
from app.features.subraces.crud.schemas import SubraceCreate, SubraceResponse, SubraceUpdate
from app.models.subrace_model import Subrace


class SubraceFeatureService(
    BaseService[Subrace, SubraceCreate, SubraceUpdate, SubraceResponse, None],
):
    """Read-only cached listing for a subrace's SUBRACE-source features."""

    repository: SubraceRepository

    cache_namespaces = ("subrace_features",)

    def __init__(self, db: AsyncSession):
        """Initialize with a subrace repository and a composed feature CRUD service."""

        super().__init__(
            repository=SubraceRepository(db),
            response_schema=SubraceResponse,
        )
        self._features = FeatureCrudService(db)

    @use_cache()
    async def list_features(self, subrace_id: int) -> list[NestedFeatureResponse]:
        """Return every SUBRACE-source feature of the subrace (cached)."""

        await self._get_or_404(subrace_id)
        return await self._features.list_for_source(FeatureSourceType.SUBRACE, subrace_id)
