"""Exceptions for GM grant and panel operations on a character."""

from fastapi import HTTPException, status


class CharacterFeatNotFoundException(HTTPException):
    """Raised when the character does not have the given feat grant."""

    def __init__(self, character_id: int, character_feat_id: int):
        self.character_id = character_id
        self.character_feat_id = character_feat_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character {character_id} has no feat grant with id {character_feat_id}.",
        )


class CharacterFeatAlreadyKnownException(HTTPException):
    """Raised when attempting to add a feat the character already has."""

    def __init__(self, character_id: int, feat_id: int):
        self.character_id = character_id
        self.feat_id = feat_id
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Character {character_id} already has feat {feat_id}.",
        )


class InvalidAbilityScoreIncreaseException(HTTPException):
    """Raised when ability_score_increase_id doesn't belong to the feat."""

    def __init__(self, feat_id: int, ability_score_increase_id: int):
        self.feat_id = feat_id
        self.ability_score_increase_id = ability_score_increase_id
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ability score increase {ability_score_increase_id} is not a valid choice for feat {feat_id}.",
        )


class FeatPrerequisiteNotMetException(HTTPException):
    """Raised when a character doesn't meet a feat's ability-score prerequisite."""

    def __init__(self, feat_id: int, ability: str, required_minimum: int, actual: int):
        self.feat_id = feat_id
        self.ability = ability
        self.required_minimum = required_minimum
        self.actual = actual
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Feat {feat_id} requires {ability} >= {required_minimum}, "
                f"but the character's effective {ability} is {actual}."
            ),
        )


class CharacterFeatureNotFoundException(HTTPException):
    """Raised when the character does not have the given feature grant."""

    def __init__(self, character_id: int, character_feature_id: int):
        self.character_id = character_id
        self.character_feature_id = character_feature_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character {character_id} has no feature grant with id {character_feature_id}.",
        )


class CharacterFeatureAlreadyKnownException(HTTPException):
    """Raised when attempting to add a feature the character already has."""

    def __init__(self, character_id: int, feature_id: int):
        self.character_id = character_id
        self.feature_id = feature_id
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Character {character_id} already has feature {feature_id}.",
        )


class GmAsiAdjustmentNotFoundException(HTTPException):
    """Raised when the character has no GM ASI adjustment with the given id."""

    def __init__(self, character_id: int, adjustment_id: int):
        self.character_id = character_id
        self.adjustment_id = adjustment_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character {character_id} has no GM ASI adjustment with id {adjustment_id}.",
        )


class CharacterItemNotFoundException(HTTPException):
    """Raised when the character does not own the given item stack."""

    def __init__(self, character_id: int, character_item_id: int):
        self.character_id = character_id
        self.character_item_id = character_item_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character {character_id} owns no item stack with id {character_item_id}.",
        )


class SkillProficiencyNotFoundException(HTTPException):
    """
    Raised when the character has no proficiency row for the given skill —
    expertise can only be toggled on an existing proficiency.
    """

    def __init__(self, character_id: int, skill_id: int):
        self.character_id = character_id
        self.skill_id = skill_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character {character_id} has no proficiency in skill {skill_id}.",
        )


class LevelTiedAsiChoiceException(HTTPException):
    """
    Raised when attempting to remove an ASI choice that is tied to a
    class level — those are managed by the level-up endpoint, not the GM
    panel (only free-form GM adjustments, ``class_level IS NULL``, can be
    removed).
    """

    def __init__(self, character_id: int, adjustment_id: int, class_level: int):
        self.character_id = character_id
        self.adjustment_id = adjustment_id
        self.class_level = class_level
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"ASI choice {adjustment_id} on character {character_id} is tied to class "
                f"level {class_level}; only GM adjustments (no class level) can be removed."
            ),
        )
