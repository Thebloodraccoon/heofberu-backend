"""Exceptions for the character progression sub-domain."""

from app.core.exceptions import AppError


class BackgroundAlreadySetException(AppError):
    """Raised when trying to set a background on a character that already has one."""

    status_code = 409

    def __init__(self, character_id: int, background_id: int):
        """Initialize with the character and background ids."""

        self.character_id = character_id
        self.background_id = background_id
        super().__init__(
            f"Character {character_id} already has background {background_id}. A background "
            "is fixed once chosen — full re-choosing is only possible through "
            f"POST /characters/{character_id}/rebuild."
        )


class BackgroundItemChoicesNotSupportedException(AppError):
    """Raised when a background with starting-equipment choice groups is set after character creation (no "pick N of M" surface exists there)."""

    status_code = 400

    def __init__(self, background_id: int):
        """Initialize with the background id."""

        self.background_id = background_id
        super().__init__(
            f"Background {background_id} defines starting-equipment choice groups, which cannot "
            "be answered when setting a background after character creation."
        )


class CharacterAlreadyAtMaxLevelException(AppError):
    """Raised when trying to level up a character already at its GM-set maximum level."""

    status_code = 400

    def __init__(self, character_id: int, max_level: int = 20):
        """Initialize with the character id and cap."""

        self.character_id = character_id
        self.max_level = max_level
        super().__init__(
            f"Character {character_id} has reached its maximum allowed level ({max_level}) "
            "and cannot level up until a GM raises it."
        )


class LevelUpChoiceRequiredException(AppError):
    """Raised when a level-up reaches an ASI level but no ASI/feat choice was provided."""

    status_code = 400

    def __init__(self, class_level: int):
        """Initialize with the class level."""

        self.class_level = class_level
        super().__init__(
            f"Level {class_level} grants an Ability Score Improvement — provide a `choice` with type `ASI` or `FEAT`."
        )


class LevelUpChoiceNotAllowedException(AppError):
    """Raised when an ASI/feat choice is given for a level that doesn't grant one."""

    status_code = 400

    def __init__(self, class_level: int):
        """Initialize with the class level."""

        self.class_level = class_level
        super().__init__(
            f"Level {class_level} does not grant an Ability Score Improvement, so no `choice` may be provided."
        )


class InvalidHitPointGainException(AppError):
    """Raised when an explicit HP gain at level-up is outside the class's allowed range."""

    status_code = 400

    def __init__(self, minimum: int, maximum: int):
        """Initialize with the allowed min/max."""

        super().__init__(
            f"hit_points_gained must be between {minimum} and {maximum} for this class's hit die and CON modifier."
        )


class InvalidRebuildMaxHpException(AppError):
    """Raised when a rebuild's ``max_hp`` is outside the range the new class/level allow."""

    status_code = 400

    def __init__(self, minimum: int, maximum: int):
        """Initialize with the allowed min/max."""

        self.minimum = minimum
        self.maximum = maximum
        super().__init__(
            f"max_hp must be between {minimum} and {maximum} for this class's hit die, its "
            "effective CON modifier, and the character's current level."
        )


class RebuildAsiChoicesMismatchException(AppError):
    """
    Raised when a rebuild's ``asi_choices`` do not exactly cover every
    ASI level (see ``ASI_LEVELS``) the character has already reached.
    """

    status_code = 400

    def __init__(self, required_levels: list[int], provided_levels: list[int]):
        """Initialize with the required and provided ASI class levels."""

        self.required_levels = required_levels
        self.provided_levels = provided_levels
        super().__init__(
            f"asi_choices must resolve exactly the ASI levels reached at the character's current "
            f"level {sorted(required_levels)}; got {sorted(provided_levels)}."
        )
