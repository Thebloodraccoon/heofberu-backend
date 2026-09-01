"""Subrace image service: upload/remove a subrace's catalog image."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RecordNotFoundError
from app.core.storage.service import ImageStorageService
from app.features.subraces.cache import invalidate_subrace_cache
from app.features.subraces.crud.repository import SubraceRepository

logger = logging.getLogger(__name__)

ENTITY = "subraces"


class SubraceImageService:
    """Upload/remove a subrace's catalog image via Supabase Storage."""

    def __init__(self, db: AsyncSession, storage: ImageStorageService):
        """Initialize with a subrace repository and the shared image storage service."""

        self._repository = SubraceRepository(db)
        self._storage = storage

    async def upload_image(
        self,
        subrace_id: int,
        content: bytes,
        content_type: str,
    ) -> str:
        """Upload ``content`` as the subrace's image and persist its public URL."""

        subrace = await self._repository.get_by_id(subrace_id)
        if subrace is None:
            raise RecordNotFoundError(model_name="Subrace", model_id=str(subrace_id))

        url = await self._storage.upload_image(ENTITY, subrace_id, content, content_type)
        await self._repository.update(subrace, {"image_url": url})
        await self._invalidate_cache(subrace_id)

        return url

    async def delete_image(self, subrace_id: int) -> None:
        """Remove the subrace's image from storage and clear its ``image_url``."""

        subrace = await self._repository.get_by_id(subrace_id)
        if subrace is None:
            raise RecordNotFoundError(model_name="Subrace", model_id=str(subrace_id))

        await self._storage.delete_image(ENTITY, subrace_id)
        await self._repository.update(subrace, {"image_url": None})
        await self._invalidate_cache(subrace_id)

    async def _invalidate_cache(self, subrace_id: int) -> None:
        """Invalidate the shared subrace cache; failures are logged rather than raised."""

        try:
            await invalidate_subrace_cache()
        except Exception as exc:  # noqa: BLE001 - cache failure must never fail the write path
            logger.error(
                "Failed to invalidate subrace cache after mutating subrace %s: %s",
                subrace_id,
                exc,
            )