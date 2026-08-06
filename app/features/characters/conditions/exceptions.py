"""Exceptions for the character conditions sub-domain."""

from fastapi import HTTPException, status

from app.constants import ConditionType


class CharacterConditionNotFoundException(HTTPException):
    """Raised when the character is not under the given condition."""

    def __init__(self, character_id: int, condition: ConditionType):
        self.character_id = character_id
        self.condition = condition
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character {character_id} is not under condition {condition.value}.",
        )


class CharacterConditionAlreadyExistsException(HTTPException):
    """Raised when attempting to add a condition the character is already under."""

    def __init__(self, character_id: int, condition: ConditionType):
        self.character_id = character_id
        self.condition = condition
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Character {character_id} is already under condition {condition.value}.",
        )


class InvalidConditionException(HTTPException):
    """Raised when a condition's ``exhaustion_level`` violates the EXHAUSTION rules."""

    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
