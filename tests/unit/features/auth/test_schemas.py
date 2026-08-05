"""Unit tests for auth schema validators."""

import pytest

from app.core.exceptions import InvalidEmailException
from app.features.auth.schemas import RegisterRequest
from app.features.users.exceptions import InvalidPasswordException


@pytest.mark.unit
class TestRegisterRequestValidators:
    def test_invalid_email_rejected(self):
        with pytest.raises(InvalidEmailException):
            RegisterRequest(username="validname", email="not-an-email", password="password123")

    def test_short_password_rejected(self):
        with pytest.raises(InvalidPasswordException):
            RegisterRequest(username="validname", email="valid@example.com", password="short")
