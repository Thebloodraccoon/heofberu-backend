"""Race image service: upload/remove a race's catalog image."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage.service import ImageStorageService
from app.features.races.cache import invalidate_race_cache
from app.features.races.crud.repository import RaceRepository
from app.features.shared.images.service import EntityImageService


class RaceImageService(EntityImageService):
    """Upload/remove a race's image (see ``EntityImageService`` for the shared behavior)."""

    def __init__(self, db: AsyncSession, storage: ImageStorageService):
        """Initialize with a race repository and the shared image storage service."""

        super().__init__(
            RaceRepository(db),
            storage,
            entity="races",
            model_name="Race",
            invalidate_cache=invalidate_race_cache,
        )
