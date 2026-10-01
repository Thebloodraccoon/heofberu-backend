"""Exceptions for the character spells sub-domain."""

from app.core.exceptions import AppError


class CharacterSpellNotFoundException(AppError):
    """Raised when the character does not have the given spell in their known list."""

    status_code = 404

    def __init__(self, character_id: int, spell_id: int):
        """Initialize with the character and spell ids."""

        self.character_id = character_id
        self.spell_id = spell_id
        super().__init__(f"Character {character_id} does not know spell {spell_id}.")


class CharacterSpellAlreadyKnownException(AppError):
    """Raised when attempting to add a spell the character already knows."""

    status_code = 409

    def __init__(self, character_id: int, spell_id: int):
        """Initialize with the character and spell ids."""

        self.character_id = character_id
        self.spell_id = spell_id
        super().__init__(f"Character {character_id} already knows spell {spell_id}.")


class SpellNotAvailableToCharacterException(AppError):
    """Raised when the spell's class/subclass/race/subrace restrictions exclude the character. Empty lists are unrestricted on that dimension."""

    status_code = 400

    def __init__(self, character_id: int, spell_id: int):
        """Initialize with the character and spell ids."""

        self.character_id = character_id
        self.spell_id = spell_id
        super().__init__(
            f"Spell {spell_id} is not available to character {character_id}'s class, subclass, race, or subrace."
        )


class NoSpellSlotAvailableException(AppError):
    """Raised when choosing a spell would exceed the character's slot total at that spell's level."""

    status_code = 400

    def __init__(self, character_id: int, level: str):
        """Initialize with the character id and spell level."""

        self.character_id = character_id
        self.level = level
        super().__init__(
            f"Character {character_id} has no free spell slot at level "
            f"'{level}' to know another spell. Remove one first to swap it."
        )
