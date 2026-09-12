"""Subclass image service: upload/remove a subclass's catalog image."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage.service import ImageStorageService
from app.features.shared.images.service import EntityImageService
from app.features.subclasses.cache import invalidate_subclass_cache
from app.features.subclasses.crud.repository import SubclassRepository


class SubclassImageService(EntityImageService):
    """Upload/remove a subclass's image (see ``EntityImageService`` for the shared behavior)."""

    def __init__(self, db: AsyncSession, storage: ImageStorageService):
        """Initialize with a subclass repository and the shared image storage service."""

        super().__init__(
            SubclassRepository(db),
            storage,
            entity="subclasses",
            model_name="Subclass",
            invalidate_cache=invalidate_subclass_cache,
        )
