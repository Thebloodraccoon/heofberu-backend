"""Race image service: upload/remove a race's catalog image."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RecordNotFoundError
from app.core.storage.service import ImageStorageService
from app.features.races.cache import invalidate_race_cache
from app.features.races.crud.repository import RaceRepository

logger = logging.getLogger(__name__)

ENTITY = "races"


class RaceImageService:
    """Upload/remove a race's catalog image via Supabase Storage."""

    def __init__(self, db: AsyncSession, storage: ImageStorageService):
        """Initialize with a race repository and the shared image storage service."""

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
        await self._invalidate_cache(race_id)

        return url

    async def delete_image(self, race_id: int) -> None:
        """Remove the race's image from storage and clear its ``image_url``."""

        race = await self._repository.get_by_id(race_id)
        if race is None:
            raise RecordNotFoundError(model_name="Race", model_id=str(race_id))

        await self._storage.delete_image(ENTITY, race_id)
        await self._repository.update(race, {"image_url": None})
        await self._invalidate_cache(race_id)

    async def _invalidate_cache(self, race_id: int) -> None:
        """Invalidate the shared race cache; failures are logged rather than raised."""

        try:
            await invalidate_race_cache()
        except Exception as exc:  # noqa: BLE001 - cache failure must never fail the write path
            logger.error(
                "Failed to invalidate race cache after mutating race %s: %s",
                race_id,
                exc,
            )
