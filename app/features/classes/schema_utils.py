"""Validation helpers shared by the class and subclass request schemas."""

from collections.abc import Hashable, Sequence
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, field_validator, model_validator

NAME_MAX_LENGTH = 100
DESCRIPTION_MAX_LENGTH = 10_000
IMAGE_URL_MAX_LENGTH = 512


def ensure_unique(values: Sequence[Hashable], label: str) -> Sequence[Hashable]:
    """Reject duplicate entries; ``label`` names the entries in the error message."""

    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {label} are not allowed.")

    return values


def unique_items(field: str, label: str) -> Any:
    """Build a ``field_validator`` that rejects duplicates in the list field ``field``."""

    def check(cls, value):
        return ensure_unique(value, label)

    return field_validator(field)(check)


def validate_image_url(value: str | None) -> str | None:
    """Accept ``None`` or an absolute http(s) URL (blocks ``javascript:``/``data:`` style values)."""

    if value is None:
        return value

    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("image_url must be an absolute http(s) URL.")

    return value


def reject_explicit_nulls(model: BaseModel, *, nullable: frozenset[str] = frozenset()) -> None:
    """
    PATCH guard: a field that was sent explicitly must not be ``null`` unless it
    is in ``nullable`` (the column is NOT NULL, so ``null`` would end in a 500).
    """

    for name in model.model_fields_set:
        if name not in nullable and getattr(model, name) is None:
            raise ValueError(f"{name} cannot be null.")


def null_guard(nullable: frozenset[str] = frozenset()) -> Any:
    """Build the ``model_validator(mode="after")`` that applies :func:`reject_explicit_nulls`."""

    def check(self):
        reject_explicit_nulls(self, nullable=nullable)
        return self

    return model_validator(mode="after")(check)
