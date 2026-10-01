"""Unit tests for auth schema validators."""

from pydantic import ValidationError
import pytest

from app.core.exceptions import InvalidEmailException
from app.features.auth.schemas import ForgotPasswordRequest, LoginRequest, RegisterRequest, ResetPasswordRequest
from app.features.users.exceptions import InvalidPasswordException


@pytest.mark.unit
class TestRegisterRequestValidators:
    def test_invalid_email_rejected(self):
        with pytest.raises(InvalidEmailException):
            RegisterRequest(username="validname", email="not-an-email", password="password123")

    def test_short_password_rejected(self):
        with pytest.raises(InvalidPasswordException):
            RegisterRequest(username="validname", email="valid@example.com", password="short")

    def test_password_over_72_bytes_rejected(self):
        with pytest.raises(InvalidPasswordException):
            RegisterRequest(username="validname", email="valid@example.com", password="a" * 73)

    def test_username_rules_apply(self):
        with pytest.raises(ValidationError, match="Username must be between 3 and 32"):
            RegisterRequest(username="ab", email="valid@example.com", password="password123")

    def test_email_normalized(self):
        request = RegisterRequest(username="validname", email=" Valid@Example.com", password="password123")

        assert request.email == "valid@example.com"


@pytest.mark.unit
class TestEmailNormalizationOnEveryPath:
    def test_login(self):
        assert LoginRequest(email="A@Example.com ", password="x").email == "a@example.com"

    def test_forgot_password(self):
        assert ForgotPasswordRequest(email=" A@Example.com").email == "a@example.com"

    def test_invalid_email_on_login_and_forgot(self):
        with pytest.raises(InvalidEmailException):
            LoginRequest(email="nope", password="x")
        with pytest.raises(InvalidEmailException):
            ForgotPasswordRequest(email="nope")


@pytest.mark.unit
class TestPasswordBounds:
    def test_login_does_not_enforce_the_minimum_but_bounds_the_size(self):
        assert LoginRequest(email="a@example.com", password="x")
        with pytest.raises(ValidationError):
            LoginRequest(email="a@example.com", password="a" * 1025)

    def test_reset_enforces_both_bounds(self):
        with pytest.raises(InvalidPasswordException):
            ResetPasswordRequest(token="t", new_password="short", confirm_password="short")
        with pytest.raises(InvalidPasswordException):
            ResetPasswordRequest(token="t", new_password="a" * 73, confirm_password="a" * 73)

    def test_reset_requires_matching_passwords(self):
        with pytest.raises(InvalidPasswordException, match="do not match"):
            ResetPasswordRequest(token="t", new_password="password123", confirm_password="password124")
