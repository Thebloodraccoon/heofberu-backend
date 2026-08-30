"""Exceptions for feat grants on a character (GM grants and level-up alike)."""

from app.core.exceptions import AppError


class CharacterFeatAlreadyKnownException(AppError):
    """Raised when attempting to add a feat the character already has."""

    status_code = 409

    def __init__(self, character_id: int, feat_id: int):
        self.character_id = character_id
        self.feat_id = feat_id
        super().__init__(f"Character {character_id} already has feat {feat_id}.")


class InvalidAbilityScoreIncreaseException(AppError):
    """Raised when ability_score_increase_id doesn't belong to the feat."""

    status_code = 400

    def __init__(self, feat_id: int, ability_score_increase_id: int):
        self.feat_id = feat_id
        self.ability_score_increase_id = ability_score_increase_id
        super().__init__(
            f"Ability score increase {ability_score_increase_id} is not a valid choice for feat {feat_id}."
        )


class FeatAsiChoiceRequiredException(AppError):
    """
    Raised when granting (or taking at level-up) a feat that offers
    ability-score increases without picking one — the choice must be
    explicit so the granted points are never silently lost.
    """

    status_code = 422

    def __init__(self, feat_id: int, choices: int):
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
        self.feat_id = feat_id
        self.ability = ability
        self.required_minimum = required_minimum
        self.actual = actual
        super().__init__(
            f"Feat {feat_id} requires {ability} >= {required_minimum}, "
            f"but the character's effective {ability} is {actual}."
        )