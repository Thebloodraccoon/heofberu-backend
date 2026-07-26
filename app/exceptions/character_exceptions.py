from fastapi import HTTPException, status


class CharacterNotFoundException(HTTPException):
    """Raised when a character with the given ID does not exist."""

    def __init__(self, character_id: int):
        self.character_id = character_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character with id {character_id} not found.",
        )


class CharacterAccessDeniedException(HTTPException):
    """Raised when a non-GM user tries to access a character they don't own."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this character.",
        )


class InvalidHpUpdateException(HTTPException):
    """Raised when an HP update request is malformed (e.g. mixes delta with
    absolute values, or provides neither)."""

    def __init__(self, message: str = "Provide either 'delta' or an absolute HP value, not both."):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


class InvalidRestTypeException(HTTPException):
    """Raised when the rest type is not one of the supported values."""

    def __init__(self, rest_type: str):
        self.rest_type = rest_type
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid rest type: '{rest_type}'. Expected 'short' or 'long'.",
        )


class InvalidSpellLevelException(HTTPException):
    """Raised when a spell slot level is not a recognized spell level."""

    def __init__(self, level: str):
        self.level = level
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid spell level: '{level}'.",
        )


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


class InvalidSkillIdsException(HTTPException):
    """Raised when one or more provided skill IDs do not correspond to existing skills."""

    def __init__(self, skill_ids: list[int]):
        self.skill_ids = skill_ids
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid skill id(s): {skill_ids}",
        )


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


class AttackNotFoundException(HTTPException):
    """Raised when an attack with the given ID does not exist on this character."""

    def __init__(self, character_id: int, attack_id: int):
        self.character_id = character_id
        self.attack_id = attack_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attack {attack_id} not found for character {character_id}.",
        )


class InvalidRollRequestException(HTTPException):
    """Raised when a roll-check/roll-attack request is malformed (e.g. neither
    skill_id nor ability provided, or an unrecognized check type)."""

    def __init__(self, message: str = "Invalid roll request."):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
