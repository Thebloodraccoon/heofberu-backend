"""Race-specific application exceptions."""

from app.core.exceptions import AppError


class RaceNotFoundException(AppError):
    """Raised when a race with the given ID does not exist."""

    status_code = 404

    def __init__(self, race_id: int):
        self.race_id = race_id
        super().__init__(f"Race with id {race_id} not found.")


class SubraceNotFoundException(AppError):
    """Raised when a subrace with the given ID does not exist under the given race."""

    status_code = 404

    def __init__(self, race_id: int, subrace_id: int):
        self.race_id = race_id
        self.subrace_id = subrace_id
        super().__init__(f"Subrace with id {subrace_id} not found for race {race_id}.")
