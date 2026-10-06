"""Class image service: upload/remove a class's catalog image."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage.service import ImageStorageService
from app.features.classes.cache import invalidate_class_cache
from app.features.classes.crud.repository import ClassRepository
from app.features.shared.images.service import EntityImageService


class ClassImageService(EntityImageService):
    """Upload/remove a class's image (see ``EntityImageService`` for the shared behavior)."""

    def __init__(self, db: AsyncSession, storage: ImageStorageService):
        """Initialize with a class repository and the shared image storage service."""

        super().__init__(
            ClassRepository(db),
            storage,
            entity="classes",
            model_name="Class",
            invalidate_cache=invalidate_class_cache,
        )
