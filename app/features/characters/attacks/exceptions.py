from fastapi import HTTPException, status


class AttackNotFoundException(HTTPException):
    """
    Raised when an attack with the given ID does not exist on this character.

    Used by both the attacks sub-domain (CRUD) and the rolls sub-domain
    (attack roll lookups).
    """

    def __init__(self, character_id: int, attack_id: int):
        self.character_id = character_id
        self.attack_id = attack_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attack {attack_id} not found for character {character_id}.",
        )
