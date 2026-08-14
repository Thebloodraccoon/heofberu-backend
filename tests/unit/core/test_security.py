"""Unit tests for password hashing helpers."""

import pytest

from app.core.security.password import get_password_hash, verify_password


@pytest.mark.unit
class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        hashed = get_password_hash("password123")

        assert hashed != "password123"
        assert "password123" not in hashed

    def test_verify_password_roundtrip(self):
        hashed = get_password_hash("correct horse battery staple")

        assert verify_password("correct horse battery staple", hashed) is True

    def test_verify_wrong_password_fails(self):
        hashed = get_password_hash("password123")

        assert verify_password("wrongpassword", hashed) is False

    def test_hashes_are_salted(self):
        first = get_password_hash("same-password")
        second = get_password_hash("same-password")

        assert first != second
        assert verify_password("same-password", first) is True
        assert verify_password("same-password", second) is True
