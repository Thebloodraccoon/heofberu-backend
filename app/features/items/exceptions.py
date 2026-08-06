"""Item-specific HTTP exceptions."""

from fastapi import HTTPException, status


class ItemNotFoundException(HTTPException):
    """Raised when an item with the given ID does not exist."""

    def __init__(self, item_id: int):
        self.item_id = item_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_id} not found.",
        )
