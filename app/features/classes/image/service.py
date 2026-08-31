"""Class image service: upload/remove a class's catalog image."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RecordNotFoundError
from app.core.storage.service import ImageStorageService
from app.features.classes.cache import invalidate_class_cache
from app.features.classes.crud.repository import ClassRepository

ENTITY = "classes"


class ClassImageService:
    """
    Upload/remove a class's image.

    The image is stored in Supabase under the ``classes`` folder (pinned to
    ``classes/{class_id}.{ext}``) and its public URL is persisted on the
    class's ``image_url`` column. DB writes flow through ``ClassRepository``
    and the shared class cache is invalidated on every mutation.
    """

    def __init__(self, db: AsyncSession, storage: ImageStorageService):
        self._repository = ClassRepository(db)
        self._storage = storage

    async def upload_image(
        self,
        class_id: int,
        content: bytes,
        content_type: str,
    ) -> str:
        """Upload ``content`` as the class's image and persist its public URL."""

        character_class = await self._repository.get_by_id(class_id)
        if character_class is None:
            raise RecordNotFoundError(model_name="Class", model_id=str(class_id))

        url = await self._storage.upload_image(ENTITY, class_id, content, content_type)
        await self._repository.update(character_class, {"image_url": url})
        await invalidate_class_cache()

        return url

    async def delete_image(self, class_id: int) -> None:
        """Remove the class's image from storage and clear its ``image_url``."""

        character_class = await self._repository.get_by_id(class_id)
        if character_class is None:
            raise RecordNotFoundError(model_name="Class", model_id=str(class_id))

        await self._storage.delete_image(ENTITY, class_id)
        await self._repository.update(character_class, {"image_url": None})
        await invalidate_class_cache()
