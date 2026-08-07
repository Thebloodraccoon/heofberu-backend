"""Exceptions for the character items sub-domain."""

from fastapi import HTTPException, status


class CharacterItemNotFoundException(HTTPException):
    """Raised when the character does not own the given item stack."""

    def __init__(self, character_id: int, character_item_id: int):
        self.character_id = character_id
        self.character_item_id = character_item_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character {character_id} owns no item stack with id {character_item_id}.",
        )
