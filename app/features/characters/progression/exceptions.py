"""Exceptions for the character progression sub-domain."""

from app.core.exceptions import AppError


class CharacterRebuildNotImplementedException(AppError):
    """Raised when the point-rebuild endpoint is hit before it is implemented."""

    status_code = 501

    def __init__(self, character_id: int):
        """Initialize with the character id."""

        self.character_id = character_id
        super().__init__(
            f"Character rebuild is not implemented yet. A full class/race change will be "
            f"available as a rebuild of character {character_id}; for now only a subclass, "
            "subrace, or background can be added while it is still unset."
        )


class BackgroundAlreadySetException(AppError):
    """Raised when trying to set a background on a character that already has one."""

    status_code = 409

    def __init__(self, character_id: int, background_id: int):
        """Initialize with the character and background ids."""

        self.character_id = character_id
        self.background_id = background_id
        super().__init__(
            f"Character {character_id} already has background {background_id}. A background "
            "is fixed once chosen — full re-choosing will be possible through the (future) "
            "rebuild endpoint."
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


class InvalidASIException(AppError):
    """Raised when an ASI choice is structurally invalid (bad total or duplicates)."""

    status_code = 400

    def __init__(self, detail: str):
        """Initialize with the failure detail."""

        super().__init__(detail)


class AbilityScoreCapExceededException(AppError):
    """Raised when an ASI would push an ability score above the 20 cap."""

    status_code = 400

    def __init__(self, ability: str, current_total: int, requested: int):
        """Initialize with the ability and its current/requested totals."""

        self.ability = ability
        self.current_total = current_total
        self.requested = requested
        super().__init__(
            f"Cannot increase {ability} to {requested}: the effective score is already {current_total} "
            "and cannot exceed the cap of 20."
        )


class InvalidHitPointGainException(AppError):
    """Raised when an explicit HP gain at level-up is outside the class's allowed range."""

    status_code = 400

    def __init__(self, minimum: int, maximum: int):
        """Initialize with the allowed min/max."""

        super().__init__(
            f"hit_points_gained must be between {minimum} and {maximum} for this class's hit die and CON modifier."
        )
