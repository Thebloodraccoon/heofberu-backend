"""Subclass feature service: read-only, cached listing for SUBCLASS-source features."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.core.cache import use_cache
from app.features.subclasses.crud.repository import SubclassRepository
from app.features.subclasses.crud.schemas import SubclassCreate, SubclassResponse, SubclassUpdate
from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.features.crud.service import FeatureCrudService
from app.models.subclass_model import Subclass


class SubclassFeatureService(
    BaseService[Subclass, SubclassCreate, SubclassUpdate, SubclassResponse, None],
):
    """
    Read-only service for a subclass's SUBCLASS-source features.

    Write endpoints have been removed — features are managed centrally
    through the features catalog. This service only provides the cached
    ``list_features`` for the ``GET /classes/subclasses/features`` read
    endpoint: the list is cached under the dedicated ``subclass_features``
    namespace, which the central feature writes invalidate (only for this
    subclass's list) via ``FeatureCrudService``.
    """

    repository: SubclassRepository

    cache_namespaces = ("subclass_features",)

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=SubclassRepository(db),
            response_schema=SubclassResponse,
        )
        self._features = FeatureCrudService(db)

    @use_cache()
    async def list_features(self, subclass_id: int) -> list[NestedFeatureResponse]:
        """Return every SUBCLASS-source feature of the subclass (cached)."""

        return await self._features.list_for_source(FeatureSourceType.SUBCLASS, subclass_id)
