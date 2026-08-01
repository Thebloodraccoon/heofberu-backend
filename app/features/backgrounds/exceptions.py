from fastapi import HTTPException, status


class BackgroundNotFoundException(HTTPException):
    """Raised when a background with the given ID does not exist."""

    def __init__(self, background_id: int):
        self.background_id = background_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Background with id {background_id} not found.",
        )


class BackgroundNameAlreadyExistsException(HTTPException):
    """Raised when attempting to create/rename a background to a name that's already taken."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Background with name '{name}' already exists.",
        )


class InvalidSkillIdsException(HTTPException):
    """Raised when one or more provided skill IDs do not correspond to existing skills."""

    def __init__(self, skill_ids: list[int]):
        self.skill_ids = skill_ids
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid skill id(s): {skill_ids}",
        )
