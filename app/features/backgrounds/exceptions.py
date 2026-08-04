from fastapi import HTTPException, status


class BackgroundNotFoundException(HTTPException):
    """Raised when a background with the given ID does not exist."""

    def __init__(self, background_id: int):
        self.background_id = background_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Background with id {background_id} not found.",
        )
