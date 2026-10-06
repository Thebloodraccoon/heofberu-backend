"""Read-only, cached listing of the features a race or subrace owns."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.repository import BaseRepository
from app.core.cache import use_cache
from app.core.exceptions import RecordNotFoundError
from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.features.crud.service import FeatureCrudService


class SourceFeaturesService:
    """Subclasses set ``cache_namespaces``, ``source_type`` and ``model_name``."""

    cache_namespaces: tuple[str, ...]
    source_type: FeatureSourceType
    model_name: str

    def __init__(self, repository: BaseRepository, db: AsyncSession):
        """Bind the owner's repository (existence check) and the feature reader."""

        self.repository = repository
        self._features = FeatureCrudService(db)

    @use_cache()
    async def list_features(self, source_id: int) -> list[NestedFeatureResponse]:
        """Return every feature owned by ``source_id`` (cached); 404 when the owner is missing."""

        if not await self.repository.exists_by_id(source_id):
            raise RecordNotFoundError(model_name=self.model_name, model_id=str(source_id))

        return await self._features.list_for_source(self.source_type, source_id)
