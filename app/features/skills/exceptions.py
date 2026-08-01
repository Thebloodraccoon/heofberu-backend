from fastapi import HTTPException, status


class SkillNotFoundException(HTTPException):
    """Raised when a skill with the given ID does not exist."""

    def __init__(self, skill_id: int):
        self.skill_id = skill_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill with id {skill_id} not found.",
        )


class SkillKeyAlreadyExistsException(HTTPException):
    """Raised when attempting to create/rename a skill to a key that's already taken."""

    def __init__(self, key: str):
        self.key = key
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Skill with key '{key}' already exists.",
        )


class SkillInUseException(HTTPException):
    """
    Raised when attempting to delete a skill that is still referenced by one
    or more races or classes, and therefore cannot be removed.
    """

    def __init__(self, skill_id: int):
        self.skill_id = skill_id
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Skill with id {skill_id} is still in use and cannot be deleted.",
        )
