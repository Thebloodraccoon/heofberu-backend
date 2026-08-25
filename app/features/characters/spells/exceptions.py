"""Exceptions for the character spells sub-domain."""

from app.core.exceptions import AppError


class CharacterSpellNotFoundException(AppError):
    """Raised when the character does not have the given spell in their known list."""

    status_code = 404

    def __init__(self, character_id: int, spell_id: int):
        self.character_id = character_id
        self.spell_id = spell_id
        super().__init__(f"Character {character_id} does not know spell {spell_id}.")


class CharacterSpellAlreadyKnownException(AppError):
    """Raised when attempting to add a spell the character already knows."""

    status_code = 409

    def __init__(self, character_id: int, spell_id: int):
        self.character_id = character_id
        self.spell_id = spell_id
        super().__init__(f"Character {character_id} already knows spell {spell_id}.")


class SpellNotAvailableToCharacterException(AppError):
    """

    Raised when a spell's ``available_classes`` / ``available_subclasses``
    / ``available_races`` / ``available_subraces`` restrictions (if any)
    don't include the character's class/subclass/race/subrace.

    A spell with an empty list for a dimension is unrestricted on that
    dimension (see ``SpellCreate`` for the empty-list-unrestricted
    convention) — this is only raised when at least one dimension is
    restricted and the character doesn't match it.
    """

    status_code = 400

    def __init__(self, character_id: int, spell_id: int):
        self.character_id = character_id
        self.spell_id = spell_id
        super().__init__(
            f"Spell {spell_id} is not available to character {character_id}'s class, subclass, race, or subrace."
        )


class NoSpellSlotAvailableException(AppError):
    """

    Raised when choosing a spell would exceed the character's spell slot
    total at that spell's level — a character may know at most as many
    spells of a given level as they have slots of that level.
    """

    status_code = 400

    def __init__(self, character_id: int, level: str):
        self.character_id = character_id
        self.level = level
        super().__init__(
            f"Character {character_id} has no free spell slot at level "
            f"'{level}' to know another spell. Remove one first to swap it."
        )
