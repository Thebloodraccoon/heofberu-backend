"""Exceptions for the character crud sub-domain."""

from fastapi import HTTPException, status


class InvalidHpUpdateException(HTTPException):
    """
    Raised when an HP update request is malformed (e.g. mixes delta with
    absolute values, or provides neither).
    """

    def __init__(self, message: str = "Provide either 'delta' or an absolute HP value, not both."):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


class SkillNotAvailableForClassException(HTTPException):
    """Raised when a skill_id is not in the class's available_skills list."""

    def __init__(self, class_id: int, skill_id: int):
        self.class_id = class_id
        self.skill_id = skill_id
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Skill {skill_id} is not available for class {class_id}.",
        )


class TooManySkillChoicesException(HTTPException):
    """Raised when the number of chosen skills exceeds the class's skill_choice_count."""

    def __init__(self, class_id: int, allowed: int, requested: int):
        self.class_id = class_id
        self.allowed = allowed
        self.requested = requested
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"Class {class_id} allows at most {allowed} skill choices, but {requested} were requested."),
        )
