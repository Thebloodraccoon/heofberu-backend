"""Exceptions for the character progression sub-domain."""

from fastapi import HTTPException, status


class CharacterAlreadyAtMaxLevelException(HTTPException):
    """Raised when trying to level up a character already at level 20."""

    def __init__(self, character_id: int):
        self.character_id = character_id
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Character {character_id} is already at the maximum level (20) and cannot level up.",
        )


class LevelUpChoiceRequiredException(HTTPException):
    """Raised when a level-up reaches an ASI level but no ASI/feat choice was provided."""

    def __init__(self, class_level: int):
        self.class_level = class_level
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Level {class_level} grants an Ability Score Improvement — provide a `choice` "
                "with type `ASI` or `FEAT`."
            ),
        )


class LevelUpChoiceNotAllowedException(HTTPException):
    """Raised when an ASI/feat choice is given for a level that doesn't grant one."""

    def __init__(self, class_level: int):
        self.class_level = class_level
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Level {class_level} does not grant an Ability Score Improvement, so no `choice` may be provided.",
        )


class InvalidASIException(HTTPException):
    """Raised when an ASI choice is structurally invalid (bad total or duplicates)."""

    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class AbilityScoreCapExceededException(HTTPException):
    """Raised when an ASI would push an ability score above the 20 cap."""

    def __init__(self, ability: str, current_total: int, requested: int):
        self.ability = ability
        self.current_total = current_total
        self.requested = requested
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot increase {ability} to {requested}: the effective score is already {current_total} "
                "and cannot exceed the cap of 20."
            ),
        )


class InvalidHitPointGainException(HTTPException):
    """Raised when an explicit HP gain at level-up is outside the class's allowed range."""

    def __init__(self, minimum: int, maximum: int):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"hit_points_gained must be between {minimum} and {maximum} for this class's hit die and CON modifier.",
        )
