"""Subclass image service: upload/remove a subclass's catalog image."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RecordNotFoundError
from app.core.storage.service import ImageStorageService
from app.features.subclasses.cache import invalidate_subclass_cache
from app.features.subclasses.crud.repository import SubclassRepository

logger = logging.getLogger(__name__)

ENTITY = "subclasses"


class SubclassImageService:
    """
    Upload/remove a subclass's image.

    The image is stored in Supabase under ``subclasses/{subclass_id}.{ext}``
    and the public URL is persisted on the subclass's ``image_url`` column.
    The shared subclass cache is invalidated on every mutation.
    """

    def __init__(self, db: AsyncSession, storage: ImageStorageService):
        """Initialize the service with a repository and the image storage backend."""

        self._repository = SubclassRepository(db)
        self._storage = storage

    async def upload_image(
        self,
        subclass_id: int,
        content: bytes,
        content_type: str,
    ) -> str:
        """Upload ``content`` as the subclass's image and persist its public URL."""

        subclass = await self._repository.get_by_id(subclass_id)
        if subclass is None:
            raise RecordNotFoundError(model_name="Subclass", model_id=str(subclass_id))

        url = await self._storage.upload_image(ENTITY, subclass_id, content, content_type)
        await self._repository.update(subclass, {"image_url": url})
        await self._invalidate_cache(subclass_id)

        return url

    async def delete_image(self, subclass_id: int) -> None:
        """Remove the subclass's image from storage and clear its ``image_url``."""

        subclass = await self._repository.get_by_id(subclass_id)
        if subclass is None:
            raise RecordNotFoundError(model_name="Subclass", model_id=str(subclass_id))

        await self._storage.delete_image(ENTITY, subclass_id)
        await self._repository.update(subclass, {"image_url": None})
        await self._invalidate_cache(subclass_id)

    async def _invalidate_cache(self, subclass_id: int) -> None:
        """
        Invalidate the shared subclass cache without letting a failure
        surface as a request error (the DB write has already committed).
        """

        try:
            await invalidate_subclass_cache()
        except Exception as exc:  # noqa: BLE001 - cache failure must never fail the write path
            logger.error(
                "Failed to invalidate subclass cache after mutating subclass %s: %s",
                subclass_id,
                exc,
            )
