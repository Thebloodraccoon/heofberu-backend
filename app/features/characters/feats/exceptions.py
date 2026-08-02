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
    """
    Raised when ``ability_score_increase_id`` doesn't correspond to an
    existing ``FeatAbilityScoreIncrease``, or belongs to a different
    feat than the one being granted/already granted.
    """

    def __init__(self, feat_id: int, ability_score_increase_id: int):
        self.feat_id = feat_id
        self.ability_score_increase_id = ability_score_increase_id
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"Ability score increase {ability_score_increase_id} is not a valid choice for feat {feat_id}."),
        )


class FeatPrerequisiteNotMetException(HTTPException):
    """
    Raised when a character doesn't meet a feat's ability-score
    prerequisite (checked against effective, post-bonus ability scores).
    """

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
