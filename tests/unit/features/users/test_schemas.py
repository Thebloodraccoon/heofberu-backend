"""Unit tests for user schema validators."""

from pydantic import ValidationError
import pytest

from app.core.exceptions import InvalidEmailException
from app.features.users.exceptions import InvalidPasswordException
from app.features.users.schemas import UserCreate, UserProfileUpdate, UserUpdate


@pytest.mark.unit
class TestUserValidators:
    def test_invalid_email_rejected(self):
        with pytest.raises(InvalidEmailException):
            UserCreate(username="validname", email="not-an-email", password="password123")

    def test_short_password_rejected(self):
        with pytest.raises(InvalidPasswordException):
            UserCreate(username="validname", email="valid@example.com", password="short")

    def test_password_over_72_bytes_rejected(self):
        with pytest.raises(InvalidPasswordException):
            UserCreate(username="validname", email="valid@example.com", password="a" * 73)

    def test_multibyte_password_counts_bytes_not_characters(self):
        with pytest.raises(InvalidPasswordException):
            UserCreate(username="validname", email="valid@example.com", password="я" * 37)

        assert UserCreate(username="validname", email="valid@example.com", password="я" * 36)

    def test_short_username_rejected(self):
        with pytest.raises(ValidationError, match="Username must be between 3 and 32"):
            UserCreate(username="ab", email="valid@example.com", password="password123")

    def test_username_with_invalid_characters_rejected(self):
        with pytest.raises(ValidationError, match="letters, numbers, underscores, and hyphens"):
            UserCreate(username="bad name", email="valid@example.com", password="password123")

    def test_email_is_stripped_and_lowercased(self):
        user = UserCreate(username="validname", email="  Valid@Example.COM ", password="password123")

        assert user.email == "valid@example.com"

    def test_overlong_email_rejected(self):
        with pytest.raises(InvalidEmailException):
            UserCreate(username="validname", email="a" * 250 + "@example.com", password="password123")

    def test_free_text_limits(self):
        with pytest.raises(ValidationError):
            UserCreate(username="validname", email="valid@example.com", password="password123", phone="1" * 101)
        with pytest.raises(ValidationError):
            UserCreate(username="validname", email="valid@example.com", password="password123", bio="b" * 5001)


@pytest.mark.unit
class TestUserUpdateValidators:
    def test_user_update_with_nothing_rejected(self):
        with pytest.raises(ValidationError, match="At least one updatable field"):
            UserUpdate()

    def test_profile_update_with_nothing_rejected(self):
        with pytest.raises(ValidationError, match="At least one updatable field"):
            UserProfileUpdate()

    @pytest.mark.parametrize("field", ["username", "email", "role"])
    def test_explicit_null_in_required_field_rejected(self, field):
        with pytest.raises(ValidationError, match="cannot be null"):
            UserUpdate.model_validate({field: None, "bio": "x"})

    @pytest.mark.parametrize("field", ["username", "email"])
    def test_profile_update_null_in_required_field_rejected(self, field):
        with pytest.raises(ValidationError, match="cannot be null"):
            UserProfileUpdate.model_validate({field: None, "bio": "x"})

    def test_explicit_null_clears_a_nullable_field(self):
        update = UserUpdate.model_validate({"bio": None})

        assert update.model_dump(exclude_unset=True) == {"bio": None}

    def test_unknown_fields_rejected(self):
        with pytest.raises(ValidationError):
            UserUpdate.model_validate({"bio": "x", "password": "secret-password"})

    def test_role_is_not_accepted_in_profile_update(self):
        with pytest.raises(ValidationError):
            UserProfileUpdate.model_validate({"role": "gm"})

    @pytest.mark.parametrize("body", [[], "text", 5, None])
    def test_non_object_body_is_a_validation_error_not_a_type_error(self, body):
        with pytest.raises(ValidationError):
            UserUpdate.model_validate(body)

    def test_update_normalizes_email(self):
        assert UserUpdate(email=" A@B.io ").email == "a@b.io"

    def test_only_sent_fields_are_dumped(self):
        update = UserProfileUpdate(bio="hello")

        assert update.model_dump(exclude_unset=True) == {"bio": "hello"}
