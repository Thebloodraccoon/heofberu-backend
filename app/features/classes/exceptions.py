from fastapi import HTTPException, status


class ClassNotFoundException(HTTPException):
    """Raised when a class with the given ID does not exist."""

    def __init__(self, class_id: int):
        self.class_id = class_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Class with id {class_id} not found.",
        )


class ClassNameAlreadyExistsException(HTTPException):
    """Raised when attempting to create/rename a class to a name that's already taken."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Class with name '{name}' already exists.",
        )


class ClassInUseException(HTTPException):
    """
    Raised when attempting to delete a class that is still assigned to one
    or more characters, and therefore cannot be removed.
    """

    def __init__(self, class_id: int):
        self.class_id = class_id
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Class with id {class_id} is still in use and cannot be deleted.",
        )
