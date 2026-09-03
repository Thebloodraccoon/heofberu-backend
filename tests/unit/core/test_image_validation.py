"""Unit tests for catalog image validation (no external storage calls)."""

import pytest

from app.core.exceptions import AppError
from app.core.storage.service import (
    ALLOWED_IMAGE_CONTENT_TYPES,
    IMAGE_MAX_BYTES,
    _ensure_valid,
    _matches_magic_bytes,
)


class TestEnsureValid:
    def test_accepts_valid_png(self):
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 10
        assert _ensure_valid("image/png", png) == "png"

    def test_accepts_valid_jpeg(self):
        assert _ensure_valid("image/jpeg", b"\xff\xd8\xff\xe0") == "jpg"

    def test_accepts_valid_gif(self):
        assert _ensure_valid("image/gif", b"GIF89a" + b"\x00" * 10) == "gif"

    def test_accepts_valid_webp(self):
        webp = b"RIFF" + b"\x00" * 4 + b"WEBP"
        assert _ensure_valid("image/webp", webp) == "webp"

    def test_rejects_unsupported_content_type(self):
        with pytest.raises(AppError):
            _ensure_valid("text/plain", b"hello")

    def test_rejects_empty_content(self):
        with pytest.raises(AppError):
            _ensure_valid("image/png", b"")

    def test_rejects_oversized_content(self):
        with pytest.raises(AppError):
            _ensure_valid("image/png", b"\x89PNG\r\n\x1a\n" + b"\x00" * (IMAGE_MAX_BYTES + 1))

    def test_rejects_content_type_mismatch(self):
        with pytest.raises(AppError):
            _ensure_valid("image/png", b"this is not a png at all")

    def test_all_content_types_have_extension(self):
        for content_type, ext in ALLOWED_IMAGE_CONTENT_TYPES.items():
            assert isinstance(ext, str) and len(ext) >= 3


class TestMatchesMagicBytes:
    def test_jpeg_signature(self):
        assert _matches_magic_bytes("image/jpeg", b"\xff\xd8\xff")

    def test_png_signature(self):
        assert _matches_magic_bytes("image/png", b"\x89PNG\r\n\x1a\n")

    def test_webp_signature_requires_webp_tag(self):
        assert not _matches_magic_bytes("image/webp", b"RIFF" + b"\x00" * 4 + b"XXXX")
        assert _matches_magic_bytes("image/webp", b"RIFF" + b"\x00" * 4 + b"WEBP")
