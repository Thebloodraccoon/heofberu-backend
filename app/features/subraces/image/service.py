"""Subrace image service: upload/remove a subrace's catalog image."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RecordNotFoundError
from app.core.storage.service import ImageStorageService
from app.features.subraces.cache import invalidate_subrace_cache
from app.features.subraces.crud.repository import SubraceRepository

ENTITY = "subraces"


class SubraceImageService:
    """
    Upload/remove a subrace's image.

    The image is stored in Supabase under the ``subraces`` folder (pinned to
    ``subraces/{subrace_id}.{ext}``) and its public URL is persisted on the
    subrace's ``image_url`` column. DB writes flow through
    ``SubraceRepository`` and the shared subrace cache is invalidated on
    every mutation.
    """

    def __init__(self, db: AsyncSession, storage: ImageStorageService):
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
        await invalidate_subrace_cache()

        return url

    async def delete_image(self, subrace_id: int) -> None:
        """Remove the subrace's image from storage and clear its ``image_url``."""

        subrace = await self._repository.get_by_id(subrace_id)
        if subrace is None:
            raise RecordNotFoundError(model_name="Subrace", model_id=str(subrace_id))

        await self._storage.delete_image(ENTITY, subrace_id)
        await self._repository.update(subrace, {"image_url": None})
        await invalidate_subrace_cache()
