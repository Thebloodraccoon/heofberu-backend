"""Shared pydantic field-validator bodies reused across article/subtype/relation schemas."""


def validate_in_list(value: str, allowed: list[str], field_name: str) -> str:
    """Reject a value not present in an open, constants-defined list (e.g. ``ARTICLE_TYPES``)."""

    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {allowed}")

    return value


def reject_explicit_null(value, field_name: str):
    """Reject an explicit ``null`` for a PATCH field that's NOT NULL on the model (omission is fine, null isn't)."""

    if value is None:
        raise ValueError(f"{field_name} may not be null")

    return value
