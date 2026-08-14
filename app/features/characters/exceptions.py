"""Character-specific HTTP exceptions."""

from fastapi import HTTPException, status


class CharacterNotFoundException(HTTPException):
    """Raised when a character with the given ID does not exist."""

    def __init__(self, character_id: int):
        self.character_id = character_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character with id {character_id} not found.",
        )


class CharacterAccessDeniedException(HTTPException):
    """Raised when a non-GM user tries to access a character they don't own."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this character.",
        )


class BackgroundNotFoundException(HTTPException):
    """Raised when a background with the given ID does not exist."""

    def __init__(self, background_id: int):
        self.background_id = background_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Background with id {background_id} not found.",
        )
