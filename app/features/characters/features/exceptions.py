"""Exceptions for the character features sub-domain."""

from fastapi import HTTPException, status


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
