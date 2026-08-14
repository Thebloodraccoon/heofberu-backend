"""Race-specific HTTP exceptions."""

from fastapi import HTTPException, status


class RaceNotFoundException(HTTPException):
    """Raised when a race with the given ID does not exist."""

    def __init__(self, race_id: int):
        self.race_id = race_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Race with id {race_id} not found.",
        )


class SubraceNotFoundException(HTTPException):
    """Raised when a subrace with the given ID does not exist under the given race."""

    def __init__(self, race_id: int, subrace_id: int):
        self.race_id = race_id
        self.subrace_id = subrace_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subrace with id {subrace_id} not found for race {race_id}.",
        )
