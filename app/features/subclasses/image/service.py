"""Subclass image service: upload/remove a subclass's catalog image."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RecordNotFoundError
from app.core.storage.service import ImageStorageService
from app.features.subclasses.cache import invalidate_subclass_cache
from app.features.subclasses.crud.repository import SubclassRepository

ENTITY = "subclasses"


class SubclassImageService:
    """
    Upload/remove a subclass's image.

    The image is stored in Supabase under the ``subclasses`` folder (pinned
    to ``subclasses/{subclass_id}.{ext}``) and its public URL is persisted on
    the subclass's ``image_url`` column. DB writes flow through
    ``SubclassRepository`` and the shared subclass cache is invalidated on
    every mutation.
    """

    def __init__(self, db: AsyncSession, storage: ImageStorageService):
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
        await invalidate_subclass_cache()

        return url

    async def delete_image(self, subclass_id: int) -> None:
        """Remove the subclass's image from storage and clear its ``image_url``."""

        subclass = await self._repository.get_by_id(subclass_id)
        if subclass is None:
            raise RecordNotFoundError(model_name="Subclass", model_id=str(subclass_id))

        await self._storage.delete_image(ENTITY, subclass_id)
        await self._repository.update(subclass, {"image_url": None})
        await invalidate_subclass_cache()
