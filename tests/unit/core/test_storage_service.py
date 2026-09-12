"""
Unit tests for ``ImageStorageService``'s network-facing paths (upload/delete/
retry), with the Supabase client mocked out — no real network calls.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import AppError
from app.core.storage.service import (
    STORAGE_MAX_ATTEMPTS,
    ImageStorageService,
    _ClientState,
    _object_path,
    _public_url,
    _with_timeout_and_retry,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 10


@pytest.fixture(autouse=True)
def _reset_client_state():
    """Ensure no real client leaks between tests via the process-wide singleton."""

    _ClientState._client = None
    _ClientState._loop = None
    _ClientState._lock = None
    yield
    _ClientState._client = None
    _ClientState._loop = None
    _ClientState._lock = None


def _fake_client(bucket):
    client = MagicMock()
    client.storage.from_ = MagicMock(return_value=bucket)
    return client


@pytest.mark.unit
@pytest.mark.asyncio
class TestUploadImage:
    async def test_upload_success_returns_versioned_public_url(self, monkeypatch):
        bucket = MagicMock()
        bucket.upload = AsyncMock(return_value=None)
        monkeypatch.setattr(_ClientState, "get", AsyncMock(return_value=_fake_client(bucket)))

        service = ImageStorageService()
        url = await service.upload_image("races", 7, PNG_BYTES, "image/png")

        assert url.startswith(_public_url(_object_path("races", 7, "png")))
        assert "?v=" in url
        bucket.upload.assert_awaited_once()

    async def test_invalid_content_never_reaches_the_client(self, monkeypatch):
        bucket = MagicMock()
        bucket.upload = AsyncMock()
        monkeypatch.setattr(_ClientState, "get", AsyncMock(return_value=_fake_client(bucket)))

        service = ImageStorageService()
        with pytest.raises(AppError):
            await service.upload_image("races", 7, b"not an image", "image/png")

        bucket.upload.assert_not_awaited()

    async def test_provider_failure_raises_image_upload_error(self, monkeypatch):
        bucket = MagicMock()
        bucket.upload = AsyncMock(side_effect=RuntimeError("network exploded"))
        monkeypatch.setattr(_ClientState, "get", AsyncMock(return_value=_fake_client(bucket)))
        monkeypatch.setattr("app.core.storage.service.STORAGE_MAX_ATTEMPTS", 1)

        service = ImageStorageService()
        with pytest.raises(AppError):
            await service.upload_image("races", 7, PNG_BYTES, "image/png")


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeleteImage:
    async def test_delete_success(self, monkeypatch):
        bucket = MagicMock()
        bucket.remove = AsyncMock(return_value=None)
        monkeypatch.setattr(_ClientState, "get", AsyncMock(return_value=_fake_client(bucket)))

        service = ImageStorageService()
        await service.delete_image("races", 7)

        bucket.remove.assert_awaited_once()

    async def test_delete_failure_is_logged_not_raised(self, monkeypatch):
        """Cleanup failures must never break the caller's write path."""

        bucket = MagicMock()
        bucket.remove = AsyncMock(side_effect=RuntimeError("provider down"))
        monkeypatch.setattr(_ClientState, "get", AsyncMock(return_value=_fake_client(bucket)))
        monkeypatch.setattr("app.core.storage.service.STORAGE_MAX_ATTEMPTS", 1)

        service = ImageStorageService()
        await service.delete_image("races", 7)  # must not raise


@pytest.mark.unit
@pytest.mark.asyncio
class TestWithTimeoutAndRetry:
    async def test_succeeds_on_first_attempt(self):
        calls = []

        async def _ok():
            calls.append(1)
            return "done"

        result = await _with_timeout_and_retry(_ok, operation="test")
        assert result == "done"
        assert len(calls) == 1

    async def test_retries_then_succeeds(self, monkeypatch):
        monkeypatch.setattr("app.core.storage.service.STORAGE_RETRY_BACKOFF", 0)
        attempts = {"count": 0}

        async def _flaky():
            attempts["count"] += 1
            if attempts["count"] < 2:
                raise RuntimeError("transient")
            return "recovered"

        result = await _with_timeout_and_retry(_flaky, operation="test")
        assert result == "recovered"
        assert attempts["count"] == 2

    async def test_raises_after_exhausting_all_attempts(self, monkeypatch):
        monkeypatch.setattr("app.core.storage.service.STORAGE_RETRY_BACKOFF", 0)
        attempts = {"count": 0}

        async def _always_fails():
            attempts["count"] += 1
            raise RuntimeError("permanent")

        with pytest.raises(RuntimeError):
            await _with_timeout_and_retry(_always_fails, operation="test")
        assert attempts["count"] == STORAGE_MAX_ATTEMPTS

    async def test_retry_false_stops_after_one_attempt(self):
        attempts = {"count": 0}

        async def _always_fails():
            attempts["count"] += 1
            raise RuntimeError("permanent")

        with pytest.raises(RuntimeError):
            await _with_timeout_and_retry(_always_fails, operation="test", retry=False)
        assert attempts["count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestClientState:
    async def test_get_builds_client_once_and_reuses_it(self, monkeypatch):
        built = []

        async def _fake_create_async_client(url, key):
            client = MagicMock()
            built.append(client)
            return client

        monkeypatch.setattr("app.core.storage.service.create_async_client", _fake_create_async_client)

        first = await _ClientState.get()
        second = await _ClientState.get()

        assert first is second
        assert len(built) == 1
