"""Item-specific application exceptions."""

from app.core.exceptions import AppError


class ItemNotFoundException(AppError):
    """Raised when an item with the given ID does not exist."""

    status_code = 404

    def __init__(self, item_id: int):
        """Set the item ID and build the 404 message."""

        self.item_id = item_id
        super().__init__(f"Item with id {item_id} not found.")


class InvalidItemDataError(AppError):
    """Raised (422) when an item's fields don't fit its type or its weapon properties."""

    status_code = 422

    def __init__(self, message: str):
        """Keep the human-readable reason."""

        super().__init__(message)


class WrongItemKindError(AppError):
    """Raised (409) when a kind's endpoint is used on an item of another kind (the kind is fixed at creation)."""

    status_code = 409

    def __init__(self, item_id: int, expected: str, actual: str):
        """Name the item and both kinds."""

        super().__init__(f"Item {item_id} is a {actual} item, not a {expected} one (the kind can't change).")
