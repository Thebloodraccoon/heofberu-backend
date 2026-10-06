"""
Helpers for reading PostgreSQL error details off SQLAlchemy exceptions.

Used by the database exception handler and by repositories that turn a lost race on a
unique constraint into a domain error.
"""

from typing import Any

from sqlalchemy.exc import SQLAlchemyError

UNIQUE_VIOLATION = "23505"
FOREIGN_KEY_VIOLATION = "23503"
NOT_NULL_VIOLATION = "23502"
CHECK_VIOLATION = "23514"

_TEXT_MARKERS = (
    ("duplicate key", UNIQUE_VIOLATION),
    ("unique", UNIQUE_VIOLATION),
    ("foreign key", FOREIGN_KEY_VIOLATION),
    ("not-null", NOT_NULL_VIOLATION),
    ("not null", NOT_NULL_VIOLATION),
    ("check constraint", CHECK_VIOLATION),
)


def _driver_error(exc: SQLAlchemyError) -> Any:
    return getattr(exc, "orig", None)


def sqlstate(exc: SQLAlchemyError) -> str | None:
    """SQLSTATE of the underlying driver error (SQLAlchemy's asyncpg adapter or the raw asyncpg cause)."""

    orig = _driver_error(exc)
    for candidate in (orig, getattr(orig, "__cause__", None)):
        for attribute in ("sqlstate", "pgcode"):
            value = getattr(candidate, attribute, None)
            if isinstance(value, str) and value:
                return value

    text = str(orig if orig is not None else exc).lower()
    return next((state for marker, state in _TEXT_MARKERS if marker in text), None)


def is_unique_violation(exc: SQLAlchemyError) -> bool:
    """Whether ``exc`` is a unique-constraint violation (SQLSTATE 23505)."""

    return sqlstate(exc) == UNIQUE_VIOLATION


def constraint_name(exc: SQLAlchemyError) -> str | None:
    """Name of the violated constraint when the driver reports it."""

    orig = _driver_error(exc)
    for candidate in (orig, getattr(orig, "__cause__", None)):
        name = getattr(candidate, "constraint_name", None)
        if isinstance(name, str):
            return name

    return None
