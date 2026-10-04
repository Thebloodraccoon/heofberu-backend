"""Test helper for the ``[{effect_type, items}]`` effect-group shape the API returns."""


def effect_items(groups: list, effect_type: str) -> list:
    """Items of the ``effect_type`` group in ``groups`` (``[]`` when the bundle has no such group)."""

    return next((group["items"] for group in groups if group["effect_type"] == effect_type), [])
