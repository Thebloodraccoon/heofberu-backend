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
import logging

from supabase import AsyncClient, create_async_client

from app.core.exceptions import AppError
from app.settings import settings

logger = logging.getLogger(__name__)

#: Timeout (seconds) applied to every Supabase Storage network call.
STORAGE_CALL_TIMEOUT = 15.0

#: Number of attempts for storage calls that support retrying (1 = no retry).
STORAGE_MAX_ATTEMPTS = 3

#: Backoff (seconds) between retry attempts, multiplied by attempt number.
STORAGE_RETRY_BACKOFF = 0.5

SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_KEY = settings.SUPABASE_KEY
STORAGE_BUCKET = settings.STORAGE_BUCKET

#: Max accepted image body size (bytes), stage-tuned (5 MB dev / 2 MB prod).
IMAGE_MAX_BYTES = settings.IMAGE_UPLOAD_MAX_BYTES

#: Allowed content types for catalog images.
ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

#: Magic-byte signatures used to sanity-check that the body actually matches
#: the declared content type (clients can freely spoof the ``Content-Type``
#: header, so this is a cheap extra guard, not a full format validator).
_MAGIC_BYTES: dict[str, tuple[bytes, ...]] = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    # WebP = RIFF????WEBP — the middle 4 bytes are a file-size field, so we
    # check the RIFF header and the WEBP tag separately below.
    "image/webp": (b"RIFF",),
}


class ImageUploadError(AppError):
    """Raised when a catalog image cannot be uploaded or removed."""

    status_code = 400


class _ClientState:
    """Lazy, process-wide Supabase client kept alive across requests."""

    _lock: asyncio.Lock | None = None
    _client: AsyncClient | None = None
    _loop: asyncio.AbstractEventLoop | None = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        """
        Return a lock bound to the currently running loop.

        The lock is intentionally *not* created at class-definition time
        (module import happens before any event loop exists) and is rebuilt
        whenever the running loop changes, so it can never end up guarding a
        client rebuild on the wrong loop (e.g. across pytest-asyncio or
        Celery worker loop boundaries).
        """

        current_loop = asyncio.get_running_loop()
        if cls._lock is None or cls._loop is not current_loop:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    async def get(cls) -> AsyncClient:
        """Return the singleton async client, rebuilding it if the event loop changed."""

        lock = cls._get_lock()
        async with lock:
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
    if not _matches_magic_bytes(content_type, content):
        raise ImageUploadError(f"File content does not match the declared type {content_type!r}.")

    return ext


def _matches_magic_bytes(content_type: str, content: bytes) -> bool:
    """
    Cheaply verify ``content`` actually starts with the signature for ``content_type``.

    This is not a full format validator (it won't catch a malformed-but-correctly-
    -signed file), but it stops the trivial case of a client sending arbitrary
    bytes with a spoofed ``Content-Type`` header — worth doing since these
    files end up served back out publicly.
    """

    if content_type == "image/webp":
        return content[:4] == b"RIFF" and content[8:12] == b"WEBP"

    signatures = _MAGIC_BYTES.get(content_type)
    if not signatures:
        # No signature registered for this type — don't block on it.
        return True
    return any(content.startswith(sig) for sig in signatures)


def _object_path(entity: str, row_id: int, ext: str) -> str:
    """Return the bucket-relative object path for a row's image."""

    return f"{entity}/{row_id}.{ext}"


def _public_url(path: str) -> str:
    """Return the fully-resolvable public URL for a bucket-relative ``path``."""

    return f"{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET}/{path}"


async def _with_timeout_and_retry(coro_factory, *, operation: str, retry: bool = True):
    """
    Run a storage call with a network timeout and optional retry-with-backoff.

    ``coro_factory`` is a zero-arg callable returning a fresh coroutine each
    time, since a coroutine object can only be awaited once and a retry needs
    a new one per attempt.
    """

    attempts = STORAGE_MAX_ATTEMPTS if retry else 1
    last_exc: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return await asyncio.wait_for(coro_factory(), timeout=STORAGE_CALL_TIMEOUT)
        except asyncio.TimeoutError as exc:
            last_exc = exc
            logger.warning(
                "Supabase storage %s timed out (attempt %d/%d)",
                operation,
                attempt,
                attempts,
            )
        except Exception as exc:  # noqa: BLE001 - retry on any provider/network failure
            last_exc = exc
            logger.warning(
                "Supabase storage %s failed (attempt %d/%d): %s",
                operation,
                attempt,
                attempts,
                exc,
            )

        if attempt < attempts:
            await asyncio.sleep(STORAGE_RETRY_BACKOFF * attempt)

    assert last_exc is not None  # noqa: S101 - loop always sets it before falling through
    raise last_exc


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
            content_type: MIME type; validated against ``ALLOWED_IMAGE_CONTENT_TYPES``
                and cross-checked against the file's magic bytes.

        Returns:
            The public URL of the stored object.
        """

        ext = _ensure_valid(content_type, content)
        path = _object_path(entity, row_id, ext)
        client = await _ClientState.get()
        bucket = client.storage.from_(STORAGE_BUCKET)

        try:
            await _with_timeout_and_retry(
                lambda: bucket.upload(
                    path,
                    content,
                    {
                        "content-type": content_type,
                        "upsert": "true",
                        "cache-control": "0",
                    },
                ),
                operation=f"upload({path})",
            )
        except Exception as exc:  # noqa: BLE001 - surface any provider failure uniformly
            logger.error("Failed to upload image at %s: %s", path, exc)
            raise ImageUploadError(f"Failed to upload image: {exc}") from exc

        return f"{_public_url(path)}?v={hashlib.md5(content).hexdigest()[:8]}"

    async def delete_image(self, entity: str, row_id: int) -> None:
        """
        Remove the row's image from storage (best-effort if absent).

        The object path is current-image aware only via the extension; since a
        row pins a single image, we glob-remove the whole ``{entity}/{row_id}.*``
        namespace to be safe even if the extension changed between uploads.

        Missing objects are not an error (Supabase Storage's ``remove`` call
        does not raise for paths that don't exist — it reports them inside the
        response body instead). Genuine failures (timeouts, network errors,
        provider 5xx) are logged rather than silently swallowed, so cleanup
        failures remain visible without ever breaking the write path.
        """

        client = await _ClientState.get()
        bucket = client.storage.from_(STORAGE_BUCKET)
        paths = [f"{entity}/{row_id}.{ext}" for ext in ALLOWED_IMAGE_CONTENT_TYPES.values()]

        try:
            await _with_timeout_and_retry(
                lambda: bucket.remove(paths),
                operation=f"remove({entity}/{row_id}.*)",
            )
        except Exception as exc:  # noqa: BLE001 - deletion cleanup must never break the write path
            logger.error("Failed to delete image(s) for %s/%s: %s", entity, row_id, exc)
