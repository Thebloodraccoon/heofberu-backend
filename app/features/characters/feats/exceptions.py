"""Exceptions for feat grants and ability-score caps on a character (GM grants and level-up alike)."""

from app.core.exceptions import AppError


class CharacterFeatAlreadyKnownException(AppError):
    """Raised when attempting to add a feat the character already has."""

    status_code = 409

    def __init__(self, character_id: int, feat_id: int):
        """Initialize with the character and feat ids."""

        self.character_id = character_id
        self.feat_id = feat_id
        super().__init__(f"Character {character_id} already has feat {feat_id}.")


class InvalidAbilityScoreIncreaseException(AppError):
    """Raised when ability_score_increase_id doesn't belong to the feat."""

    status_code = 400

    def __init__(self, feat_id: int, ability_score_increase_id: int):
        """Initialize with the feat and ASI-choice ids."""

        self.feat_id = feat_id
        self.ability_score_increase_id = ability_score_increase_id
        super().__init__(
            f"Ability score increase {ability_score_increase_id} is not a valid choice for feat {feat_id}."
        )


class FeatAsiChoiceRequiredException(AppError):
    """Raised when a feat offering ASI options is granted/taken without picking one explicitly."""

    status_code = 422

    def __init__(self, feat_id: int, choices: int):
        """Initialize with the feat id and available choice count."""

        self.feat_id = feat_id
        self.choices = choices
        super().__init__(
            f"Feat {feat_id} offers {choices} ability score increase option(s); "
            "an `ability_score_increase_id` must be chosen explicitly."
        )


class FeatPrerequisiteNotMetException(AppError):
    """Raised when a character doesn't meet a feat's ability-score prerequisite."""

    status_code = 400

    def __init__(self, feat_id: int, ability: str, required_minimum: int, actual: int):
        """Initialize with the feat id, ability, and required/actual scores."""

        self.feat_id = feat_id
        self.ability = ability
        self.required_minimum = required_minimum
        self.actual = actual
        super().__init__(
            f"Feat {feat_id} requires {ability} >= {required_minimum}, "
            f"but the character's effective {ability} is {actual}."
        )


class AbilityScoreCapExceededException(AppError):
    """Raised when an increase would push an ability score above the cap."""

    status_code = 400

    def __init__(self, ability: str, current_total: int, requested: int, cap: int = 20):
        """Initialize with the ability, its current/requested totals and the cap."""

        self.ability = ability
        self.current_total = current_total
        self.requested = requested
        self.cap = cap
        super().__init__(
            f"Cannot increase {ability} to {requested}: the effective score is already {current_total} "
            f"and cannot exceed the cap of {cap}."
        )


class FeatMinLevelNotMetException(AppError):
    """Raised when a feat is taken below the character level it requires."""

    status_code = 400

    def __init__(self, feat_id: int, min_level: int, level: int):
        """Initialize with the feat id, its minimum level and the level it is taken at."""

        self.feat_id = feat_id
        self.min_level = min_level
        self.level = level
        super().__init__(f"Feat {feat_id} requires character level {min_level}, but it is taken at level {level}.")
