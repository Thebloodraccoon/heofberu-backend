"""Exceptions for the character attacks sub-domain."""

from app.core.exceptions import AppError


class AttackNotFoundException(AppError):
    """Raised when an attack with the given ID does not exist on this character."""

    status_code = 404

    def __init__(self, character_id: int, attack_id: int):
        """Initialize with the character and attack ids."""

        self.character_id = character_id
        self.attack_id = attack_id
        super().__init__(f"Attack {attack_id} not found for character {character_id}.")


class AttackLimitReachedException(AppError):
    """Raised when a character already has the maximum number of attacks."""

    status_code = 400

    def __init__(self, character_id: int, limit: int):
        """Initialize with the character id and the per-character limit."""

        self.character_id = character_id
        self.limit = limit
        super().__init__(f"Character {character_id} already has the maximum of {limit} attacks.")
