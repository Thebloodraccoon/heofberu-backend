"""Shared base for per-entity catalog image services (upload/replace/delete via Supabase Storage)."""

from collections.abc import Awaitable, Callable
import logging

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.repository import BaseRepository
from app.core.base.transaction import TransactionMixin
from app.core.exceptions import RecordNotFoundError
from app.core.storage.service import ImageStorageService
from app.settings import settings

logger = logging.getLogger(__name__)


class EntityImageService(TransactionMixin):
    """
    Upload/remove one catalog entity's image.

    The image is stored in Supabase under ``{entity}/{entity_id}.{ext}`` and
    the public URL is persisted on the row's ``image_url`` column. The
    owning capability's cache is invalidated on every mutation — a failure
    to invalidate is logged, never raised (the DB write is already committed or deferred to commit).

    Every per-entity image service (``ClassImageService``,
    ``RaceImageService``, ...) is a thin subclass that just supplies its own
    repository, entity name, and cache invalidator.
    """

    def __init__(
        self,
        repository: BaseRepository,
        storage: ImageStorageService,
        *,
        entity: str,
        model_name: str,
        invalidate_cache: Callable[[], Awaitable[None]],
    ):
        """Configure the service with its repository, the shared storage backend, and cache hook."""

        self._repository = repository
        self._storage = storage
        self._entity = entity
        self._model_name = model_name
        self._invalidate_cache_fn = invalidate_cache

    @property
    def _tx_db(self) -> AsyncSession:
        return self._repository.db

    async def upload(self, entity_id: int, image: UploadFile) -> str:
        """
        Read ``image`` off the wire, upload it, and persist its public URL.

        At most ``IMAGE_UPLOAD_MAX_BYTES + 1`` bytes are read: anything larger is
        rejected by the storage validation without buffering the whole upload.
        """

        content = await image.read(settings.IMAGE_UPLOAD_MAX_BYTES + 1)
        try:
            return await self.upload_image(entity_id, content, image.content_type or "")
        finally:
            await image.close()

    async def upload_image(self, entity_id: int, content: bytes, content_type: str) -> str:
        """Upload raw ``content`` as the entity's image and persist its public URL."""

        row = await self._get_or_404(entity_id)
        url = await self._storage.upload_image(self._entity, entity_id, content, content_type)
        async with self._atomic():
            await self._repository.update(row, {"image_url": url})
            await self._invalidate_cache(entity_id)
        return url

    async def delete_image(self, entity_id: int) -> None:
        """Remove the entity's image from storage and clear its ``image_url``."""

        row = await self._get_or_404(entity_id)
        await self._storage.delete_image(self._entity, entity_id)
        async with self._atomic():
            await self._repository.update(row, {"image_url": None})
            await self._invalidate_cache(entity_id)

    async def _get_or_404(self, entity_id: int):
        """
        Fetch the entity row (no eager-loaded relations) or raise ``RecordNotFoundError``.

        Deliberately bypasses ``self._repository.get_by_id``: that applies
        the catalog's full ``default_load_options`` (the heaviest eager-load
        tree for some catalogs), which an image swap never touches — only
        the row itself, for a single-column ``update()``.
        """

        model = self._repository.model
        row = await self._repository.db.scalar(select(model).where(model.id == entity_id))
        if row is None:
            raise RecordNotFoundError(model_name=self._model_name, model_id=str(entity_id))
        return row

    async def _invalidate_cache(self, entity_id: int) -> None:
        """Invalidate the owning capability's cache, logging (never raising) on failure."""

        try:
            await self._invalidate_cache_fn()
        except Exception as exc:  # noqa: BLE001 - cache failure must never fail the write path
            logger.error(
                "Failed to invalidate %s cache after mutating %s %s: %s",
                self._entity,
                self._entity,
                entity_id,
                exc,
            )
