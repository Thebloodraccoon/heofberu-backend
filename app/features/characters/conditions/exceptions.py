"""Exceptions for the character conditions sub-domain."""

from app.constants import ConditionType
from app.core.exceptions import AppError


class CharacterConditionNotFoundException(AppError):
    """Raised when the character is not under the given condition."""

    status_code = 404

    def __init__(self, character_id: int, condition: ConditionType):
        self.character_id = character_id
        self.condition = condition
        super().__init__(f"Character {character_id} is not under condition {condition.value}.")


class CharacterConditionAlreadyExistsException(AppError):
    """Raised when attempting to add a condition the character is already under."""

    status_code = 409

    def __init__(self, character_id: int, condition: ConditionType):
        self.character_id = character_id
        self.condition = condition
        super().__init__(f"Character {character_id} is already under condition {condition.value}.")


class InvalidConditionException(AppError):
    """Raised when a condition's ``exhaustion_level`` violates the EXHAUSTION rules."""

    status_code = 400

    def __init__(self, detail: str):
        super().__init__(detail)
