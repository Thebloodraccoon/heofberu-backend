"""Race image service: upload/remove a race's catalog image."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RecordNotFoundError
from app.core.storage.service import ImageStorageService
from app.features.races.cache import invalidate_race_cache
from app.features.races.crud.repository import RaceRepository

ENTITY = "races"


class RaceImageService:
    """
    Upload/remove a race's image.

    The image is stored in Supabase under the ``races`` folder (pinned to
    ``races/{race_id}.{ext}``) and its public URL is persisted on the race's
    ``image_url`` column. DB writes flow through ``RaceRepository`` and the
    shared race cache is invalidated on every mutation.
    """

    def __init__(self, db: AsyncSession, storage: ImageStorageService):
        self._repository = RaceRepository(db)
        self._storage = storage

    async def upload_image(
        self,
        race_id: int,
        content: bytes,
        content_type: str,
    ) -> str:
        """Upload ``content`` as the race's image and persist its public URL."""

        race = await self._repository.get_by_id(race_id)
        if race is None:
            raise RecordNotFoundError(model_name="Race", model_id=str(race_id))

        url = await self._storage.upload_image(ENTITY, race_id, content, content_type)
        await self._repository.update(race, {"image_url": url})
        await invalidate_race_cache()

        return url

    async def delete_image(self, race_id: int) -> None:
        """Remove the race's image from storage and clear its ``image_url``."""

        race = await self._repository.get_by_id(race_id)
        if race is None:
            raise RecordNotFoundError(model_name="Race", model_id=str(race_id))

        await self._storage.delete_image(ENTITY, race_id)
        await self._repository.update(race, {"image_url": None})
        await invalidate_race_cache()
