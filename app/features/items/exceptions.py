from fastapi import HTTPException, status


class ItemNotFoundException(HTTPException):
    """Raised when an item with the given ID does not exist."""

    def __init__(self, item_id: int):
        self.item_id = item_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_id} not found.",
        )


class ItemNameAlreadyExistsException(HTTPException):
    """Raised when attempting to create/rename an item to a name that's already taken."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Item with name '{name}' already exists.",
        )


class ItemInUseException(HTTPException):
    """
    Raised when attempting to delete an item that is still owned by one or
    more characters, and therefore cannot be removed — the FK on
    ``character_items.item_id`` is ``ON DELETE RESTRICT``.
    """

    def __init__(self, item_id: int):
        self.item_id = item_id
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Item with id {item_id} is still owned by one or more characters and cannot be deleted.",
        )
