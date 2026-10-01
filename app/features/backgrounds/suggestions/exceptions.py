"""Exceptions for the background suggestions sub-domain."""

from app.core.exceptions import AppError


class SuggestionNotFoundException(AppError):
    """Raised when a suggestion with the given ID does not exist on this background."""

    status_code = 404

    def __init__(self, background_id: int, suggestion_id: int):
        """Initialize with the background and suggestion ids."""

        self.background_id = background_id
        self.suggestion_id = suggestion_id
        super().__init__(f"Suggestion {suggestion_id} not found for background {background_id}.")


class LastSuggestionOfTypeError(AppError):
    """Raised (409) when a change would leave a background without any suggestion of one type."""

    status_code = 409

    def __init__(self, background_id: int, suggestion_type: str):
        """Initialize with the background and the type that would become empty."""

        self.background_id = background_id
        self.suggestion_type = suggestion_type
        super().__init__(
            f"Background {background_id} must keep at least one {suggestion_type} suggestion "
            "(character creation needs one per type)."
        )
