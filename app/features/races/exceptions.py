from fastapi import HTTPException, status


class RaceNotFoundException(HTTPException):
    """Raised when a race with the given ID does not exist."""

    def __init__(self, race_id: int):
        self.race_id = race_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Race with id {race_id} not found.",
        )


class RaceInUseException(HTTPException):
    """
    Raised when attempting to delete a race that is still assigned to one
    or more characters, and therefore cannot be removed.
    """

    def __init__(self, race_id: int):
        self.race_id = race_id
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Race with id {race_id} is still in use and cannot be deleted.",
        )


class InvalidSkillIdsException(HTTPException):
    """Raised when one or more provided skill IDs do not correspond to existing skills."""

    def __init__(self, skill_ids: list[int]):
        self.skill_ids = skill_ids
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid skill id(s): {skill_ids}",
        )
