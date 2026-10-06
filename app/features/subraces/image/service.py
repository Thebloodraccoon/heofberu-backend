"""Subrace image service: upload/remove a subrace's catalog image."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage.service import ImageStorageService
from app.features.shared.images.service import EntityImageService
from app.features.subraces.cache import invalidate_subrace_cache
from app.features.subraces.crud.repository import SubraceRepository


class SubraceImageService(EntityImageService):
    """Upload/remove a subrace's image (see ``EntityImageService`` for the shared behavior)."""

    def __init__(self, db: AsyncSession, storage: ImageStorageService):
        """Initialize with a subrace repository and the shared image storage service."""

        super().__init__(
            SubraceRepository(db),
            storage,
            entity="subraces",
            model_name="Subrace",
            invalidate_cache=invalidate_subrace_cache,
        )
