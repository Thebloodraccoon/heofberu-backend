"""Exceptions for the character attacks sub-domain."""

from app.core.exceptions import AppError


class AttackNotFoundException(AppError):
    """
    Raised when an attack with the given ID does not exist on this character.

    Used by the attacks sub-domain (CRUD).
    """

    status_code = 404

    def __init__(self, character_id: int, attack_id: int):
        self.character_id = character_id
        self.attack_id = attack_id
        super().__init__(f"Attack {attack_id} not found for character {character_id}.")
