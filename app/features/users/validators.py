"""
Single definition of the user-field input rules: emails, usernames, new passwords, profile text.

Used by the auth and users schemas through the ``Email`` / ``Username`` /
``NewPassword`` annotated types, so every input path normalizes and
validates the same way (login-only rules live in the auth schemas). Email and password failures raise the domain
exceptions (HTTP 400); username/free-text failures are regular pydantic
validation errors (HTTP 422).
"""

import re
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

from app.core.exceptions import InvalidEmailException
from app.features.users.exceptions import InvalidPasswordException

EMAIL_PATTERN = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")
EMAIL_MAX_LENGTH = 254

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9А-Яа-яЁёІіЇїЄєҐґ_-]+$")
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 32

PASSWORD_MIN_LENGTH = 8
# bcrypt silently ignores everything past 72 bytes; reject instead of hashing a truncated secret.
PASSWORD_MAX_BYTES = 72

BIO_MAX_LENGTH = 5000
CONTACT_MAX_LENGTH = 100


def normalize_email(email: str) -> str:
    """Return the canonical form of an email: stripped and lowercased."""

    return email.strip().lower()


def validate_email_value(email: str) -> str:
    """Normalize ``email`` and reject it when it is too long or not a plain address."""

    normalized = normalize_email(email)
    if len(normalized) > EMAIL_MAX_LENGTH or not EMAIL_PATTERN.match(normalized):
        raise InvalidEmailException()

    return normalized


def validate_username_value(username: str) -> str:
    """Enforce username length and allowed character set."""

    if not USERNAME_MIN_LENGTH <= len(username) <= USERNAME_MAX_LENGTH:
        raise ValueError(f"Username must be between {USERNAME_MIN_LENGTH} and {USERNAME_MAX_LENGTH} characters long")
    if not USERNAME_PATTERN.match(username):
        raise ValueError("Username can only contain letters, numbers, underscores, and hyphens")

    return username


def validate_new_password_value(password: str) -> str:
    """Enforce 8 characters minimum and bcrypt's 72-byte maximum for a password being set."""

    if len(password) < PASSWORD_MIN_LENGTH:
        raise InvalidPasswordException(f"Password must be at least {PASSWORD_MIN_LENGTH} characters long")
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise InvalidPasswordException(f"Password must be at most {PASSWORD_MAX_BYTES} bytes long")

    return password


Email = Annotated[str, AfterValidator(validate_email_value)]
Username = Annotated[str, AfterValidator(validate_username_value)]
NewPassword = Annotated[str, AfterValidator(validate_new_password_value)]

Bio = Annotated[str, StringConstraints(max_length=BIO_MAX_LENGTH)]
ContactField = Annotated[str, StringConstraints(max_length=CONTACT_MAX_LENGTH)]
