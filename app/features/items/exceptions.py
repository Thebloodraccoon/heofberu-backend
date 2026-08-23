"""Item-specific application exceptions."""

from app.core.exceptions import AppError


class ItemNotFoundException(AppError):
    """Raised when an item with the given ID does not exist."""

    status_code = 404

    def __init__(self, item_id: int):
        self.item_id = item_id
        super().__init__(f"Item with id {item_id} not found.")
