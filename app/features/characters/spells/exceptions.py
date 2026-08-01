from fastapi import HTTPException, status


class SpellSlotNotFoundException(HTTPException):
    """Raised when the character has no spell slot entry for the given level."""

    def __init__(self, character_id: int, level: str):
        self.character_id = character_id
        self.level = level
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character {character_id} has no spell slot entry for level '{level}'.",
        )


class InvalidSpellSlotUsageException(HTTPException):
    """Raised when a spell slot update would result in used < 0 or used > total."""

    def __init__(self, message: str = "Spell slot 'used' must be between 0 and 'total'."):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


class CharacterSpellNotFoundException(HTTPException):
    """Raised when the character does not have the given spell in their known list."""

    def __init__(self, character_id: int, spell_id: int):
        self.character_id = character_id
        self.spell_id = spell_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character {character_id} does not know spell {spell_id}.",
        )


class CharacterSpellAlreadyKnownException(HTTPException):
    """Raised when attempting to add a spell the character already knows."""

    def __init__(self, character_id: int, spell_id: int):
        self.character_id = character_id
        self.spell_id = spell_id
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Character {character_id} already knows spell {spell_id}.",
        )
