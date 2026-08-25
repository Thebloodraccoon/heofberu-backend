"""Exceptions for GM grant and panel operations on a character."""

from app.core.exceptions import AppError


class CharacterFeatNotFoundException(AppError):
    """Raised when the character does not have the given feat grant."""

    status_code = 404

    def __init__(self, character_id: int, character_feat_id: int):
        self.character_id = character_id
        self.character_feat_id = character_feat_id
        super().__init__(f"Character {character_id} has no feat grant with id {character_feat_id}.")


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


class CharacterFeatureNotFoundException(AppError):
    """Raised when the character does not have the given feature grant."""

    status_code = 404

    def __init__(self, character_id: int, character_feature_id: int):
        self.character_id = character_id
        self.character_feature_id = character_feature_id
        super().__init__(f"Character {character_id} has no feature grant with id {character_feature_id}.")


class CharacterFeatureAlreadyKnownException(AppError):
    """Raised when attempting to add a feature the character already has."""

    status_code = 409

    def __init__(self, character_id: int, feature_id: int):
        self.character_id = character_id
        self.feature_id = feature_id
        super().__init__(f"Character {character_id} already has feature {feature_id}.")


class GmAsiAdjustmentNotFoundException(AppError):
    """Raised when the character has no GM ASI adjustment with the given id."""

    status_code = 404

    def __init__(self, character_id: int, adjustment_id: int):
        self.character_id = character_id
        self.adjustment_id = adjustment_id
        super().__init__(f"Character {character_id} has no GM ASI adjustment with id {adjustment_id}.")


class CharacterItemNotFoundException(AppError):
    """Raised when the character does not own the given item stack."""

    status_code = 404

    def __init__(self, character_id: int, character_item_id: int):
        self.character_id = character_id
        self.character_item_id = character_item_id
        super().__init__(f"Character {character_id} owns no item stack with id {character_item_id}.")


class SkillProficiencyNotFoundException(AppError):
    """

    Raised when the character has no proficiency row for the given skill —
    expertise can only be toggled on an existing proficiency.
    """

    status_code = 404

    def __init__(self, character_id: int, skill_id: int):
        self.character_id = character_id
        self.skill_id = skill_id
        super().__init__(f"Character {character_id} has no proficiency in skill {skill_id}.")


class LevelTiedAsiChoiceException(AppError):
    """

    Raised when attempting to remove an ASI choice that is tied to a
    class level — those are managed by the level-up endpoint, not the GM
    panel (only free-form GM adjustments, ``class_level IS NULL``, can be
    removed).
    """

    status_code = 400

    def __init__(self, character_id: int, adjustment_id: int, class_level: int):
        self.character_id = character_id
        self.adjustment_id = adjustment_id
        self.class_level = class_level
        super().__init__(
            f"ASI choice {adjustment_id} on character {character_id} is tied to class "
            f"level {class_level}; only GM adjustments (no class level) can be removed."
        )


class MaxLevelCanOnlyIncreaseException(AppError):
    """

    Raised when a GM attempts to lower (or keep) a character's maximum
    allowed level — the cap can only ever move up.
    """

    status_code = 400

    def __init__(self, character_id: int, current_max_level: int):
        self.character_id = character_id
        self.current_max_level = current_max_level
        super().__init__(
            f"Character {character_id}'s maximum level is already {current_max_level}; "
            "it can only be raised, never lowered."
        )


class MaxLevelBelowCharacterLevelException(AppError):
    """

    Raised when a GM attempts to set a maximum level below the
    character's current level.
    """

    status_code = 400

    def __init__(self, character_id: int, max_level: int, character_level: int):
        self.character_id = character_id
        self.max_level = max_level
        self.character_level = character_level
        super().__init__(
            f"Cannot set maximum level {max_level} for character {character_id}: "
            f"the character is already level {character_level}."
        )
