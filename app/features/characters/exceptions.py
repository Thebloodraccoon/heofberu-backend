"""Character-specific application exceptions."""

from app.core.exceptions import AppError


class CharacterNotFoundException(AppError):
    """Raised when a character with the given ID does not exist."""

    status_code = 404

    def __init__(self, character_id: int):
        """Initialize with the missing character id."""

        self.character_id = character_id
        super().__init__(f"Character with id {character_id} not found.")


class CharacterAccessDeniedException(AppError):
    """Raised when a non-GM user tries to access a character they don't own."""

    status_code = 403

    def __init__(self):
        """Initialize with the default access-denied message."""

        super().__init__("You do not have access to this character.")


class BackgroundNotFoundException(AppError):
    """Raised when a background with the given ID does not exist."""

    status_code = 404

    def __init__(self, background_id: int):
        """Initialize with the missing background id."""

        self.background_id = background_id
        super().__init__(f"Background with id {background_id} not found.")
