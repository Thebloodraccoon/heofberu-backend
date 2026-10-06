"""Shared pydantic field-validator bodies reused across article/subtype/relation schemas."""

from collections.abc import Collection

from app.features.articles.secrets import has_nested_gm_container


def validate_in_list(value: str, allowed: Collection[str], field_name: str) -> str:
    """Reject a value not present in an open, constants-defined list (e.g. ``ARTICLE_TYPES``)."""

    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {list(allowed)}")

    return value


def reject_explicit_null(value, field_name: str):
    """Reject an explicit ``null`` for a PATCH field that's NOT NULL on the model (omission is fine, null isn't)."""

    if value is None:
        raise ValueError(f"{field_name} may not be null")

    return value


def reject_nested_gm_containers(value: str | None) -> str | None:
    """
    Reject text whose ``:::gm`` block contains another ``:::`` container.

    The database-side GM stripping (search index, snippets) can't track nesting, so such a block would leak
    its tail into search for non-GMs; keep ``:::gm`` blocks flat (a bare ``:::`` closes them).
    """

    if has_nested_gm_container(value):
        raise ValueError("a ':::gm' block must not contain another ':::' container; close it with ':::' first")

    return value


def normalize_title(title: str) -> str:
    """Trim and collapse inner whitespace; reject a blank title."""

    normalized = " ".join(title.split())
    if not normalized:
        raise ValueError("title must not be blank")

    return normalized
