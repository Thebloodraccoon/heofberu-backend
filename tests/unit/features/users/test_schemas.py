"""Unit tests for user schema validators."""

from pydantic import ValidationError
import pytest

from app.core.exceptions import InvalidEmailException
from app.features.users.exceptions import InvalidPasswordException
from app.features.users.schemas import UserCreate, UserUpdate


@pytest.mark.unit
class TestUserValidators:
    def test_invalid_email_rejected(self):
        with pytest.raises(InvalidEmailException):
            UserCreate(username="validname", email="not-an-email", password="password123")

    def test_short_password_rejected(self):
        with pytest.raises(InvalidPasswordException):
            UserCreate(username="validname", email="valid@example.com", password="short")

    def test_short_username_rejected(self):
        with pytest.raises(ValidationError, match="Username must be between 3 and 32"):
            UserCreate(username="ab", email="valid@example.com", password="password123")

    def test_username_with_invalid_characters_rejected(self):
        with pytest.raises(ValidationError, match="letters, numbers, underscores, and hyphens"):
            UserCreate(username="bad name", email="valid@example.com", password="password123")

    def test_user_update_with_all_none_rejected(self):
        with pytest.raises(ValidationError, match="At least one updatable field"):
            UserUpdate()
