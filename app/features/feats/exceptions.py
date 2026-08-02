from fastapi import HTTPException, status


class FeatNotFoundException(HTTPException):
    """Raised when a feat with the given ID does not exist."""

    def __init__(self, feat_id: int):
        self.feat_id = feat_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feat with id {feat_id} not found.",
        )


class FeatNameAlreadyExistsException(HTTPException):
    """Raised when attempting to create/rename a feat to a name that's already taken."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Feat with name '{name}' already exists.",
        )


class FeatInUseException(HTTPException):
    """
    Raised when attempting to delete a feat that is still granted to one
    or more characters, and therefore cannot be removed.
    """

    def __init__(self, feat_id: int):
        self.feat_id = feat_id
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Feat with id {feat_id} is still in use and cannot be deleted.",
        )
