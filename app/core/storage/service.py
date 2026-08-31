"""
Supabase Storage-backed image upload/delete service.

A single image per owning row (race/subrace/class/subclass): the object is
stored at ``catalog-images/{entity}/{row_id}.{ext}`` so a row owns exactly one
image and re-uploading replaces it in place. The public URL is constructed from
the project's ``SUPABASE_URL`` (Supabase's documented
``/storage/v1/object/public/{bucket}/{path}`` format).

The Supabase client is created once through a process-wide lazily-built
singleton (mirroring the cached Redis client in
``app/settings/_common.py``) so no new client is minted per request.
"""

import asyncio
import hashlib

from supabase import AsyncClient, create_async_client

from app.core.exceptions import AppError
from app.settings import settings

#: Max accepted image body size (bytes) — 5 MB.
IMAGE_MAX_BYTES = 5 * 1024 * 1024

SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_KEY = settings.SUPABASE_KEY
STORAGE_BUCKET = settings.STORAGE_BUCKET

#: Allowed content types for catalog images.
ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


class ImageUploadError(AppError):
    """Raised when a catalog image cannot be uploaded or removed."""

    status_code = 400


class _ClientState:
    """Lazy, process-wide Supabase client kept alive across requests."""

    _lock = asyncio.Lock()
    _client = None
    _loop = None

    @classmethod
    async def get(cls) -> AsyncClient:
        """Return the singleton async client, rebuilding it if the event loop changed."""

        async with cls._lock:
            current_loop = asyncio.get_running_loop()
            if cls._client is None or cls._loop is not current_loop:
                if cls._client is not None:
                    await cls._client.aclose()
                cls._client = await create_async_client(SUPABASE_URL, SUPABASE_KEY)
                cls._loop = current_loop

            return cls._client


def _ensure_valid(content_type: str, content: bytes) -> str:
    """Validate a catalog-image upload, returning the file extension."""

    ext = ALLOWED_IMAGE_CONTENT_TYPES.get(content_type or "")
    if not ext:
        raise ImageUploadError(
            f"Unsupported image content type {content_type!r}. "
            f"Allowed: {', '.join(sorted(ALLOWED_IMAGE_CONTENT_TYPES))}."
        )
    if not content:
        raise ImageUploadError("Empty file cannot be uploaded as an image.")
    if len(content) > IMAGE_MAX_BYTES:
        raise ImageUploadError(f"Image is too large: max {IMAGE_MAX_BYTES // (1024 * 1024)} MB.")

    return ext


def _object_path(entity: str, row_id: int, ext: str) -> str:
    """Return the bucket-relative object path for a row's image."""

    return f"{entity}/{row_id}.{ext}"


def _public_url(path: str) -> str:
    """Return the fully-resolvable public URL for a bucket-relative ``path``."""

    return f"{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET}/{path}"


class ImageStorageService:
    """
    Upload/delete catalog images in Supabase Storage.

    The service is stateless per request (it only uses the shared client); a
    fresh instance is cheap and is what the ``StorageServiceDep`` provides.
    """

    async def upload_image(
        self,
        entity: str,
        row_id: int,
        content: bytes,
        content_type: str,
    ) -> str:
        """
        Upload ``content`` as the row's image, replacing any previous one.

        Args:
            entity: Logical folder for the catalog (e.g. ``"races"``).
            row_id: Owning row id — pins the object path so re-uploads replace.
            content: Raw image bytes.
            content_type: MIME type; validated against ``ALLOWED_IMAGE_CONTENT_TYPES``.

        Returns:
            The public URL of the stored object.
        """

        ext = _ensure_valid(content_type, content)
        path = _object_path(entity, row_id, ext)
        client = await _ClientState.get()
        bucket = client.storage.from_(STORAGE_BUCKET)

        try:
            await bucket.upload(
                path,
                content,
                {
                    "content-type": content_type,
                    "upsert": "true",
                    "cache-control": "0",
                },
            )
        except Exception as exc:  # noqa: BLE001 - surface any provider failure uniformly
            raise ImageUploadError(f"Failed to upload image: {exc}") from exc

        return f"{_public_url(path)}?v={hashlib.md5(content).hexdigest()[:8]}"

    async def delete_image(self, entity: str, row_id: int) -> None:
        """
        Remove the row's image from storage (best-effort if absent).

        The object path is current-image aware only via the extension; since a
        row pins a single image, we glob-remove the whole ``{entity}/{row_id}.*``
        namespace to be safe even if the extension changed between uploads.
        """

        client = await _ClientState.get()
        bucket = client.storage.from_(STORAGE_BUCKET)
        try:
            await bucket.remove([f"{entity}/{row_id}.{ext}" for ext in ALLOWED_IMAGE_CONTENT_TYPES.values()])
        except Exception:  # noqa: BLE001 - deletion cleanup must never break the write path
            pass
