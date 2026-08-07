"""Character feature endpoints: record, update, and remove."""

from fastapi import APIRouter, status

from app.core.dependencies import CharacterFeatureServiceDep, CurrentUserDep
from app.features.characters.features.schemas import (
    CharacterFeatureAdd,
    CharacterFeatureResponse,
    CharacterFeatureUpdate,
)

router = APIRouter(prefix="/{character_id}/features", tags=["Character Features"])


@router.get(
    "/",
    response_model=list[CharacterFeatureResponse],
    summary="List a character's features",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
def get_character_features(
    character_id: int,
    character_feature_service: CharacterFeatureServiceDep,
    current_user: CurrentUserDep,
):
    """
    List every feature recorded on a character. GM can view any
    character's features; players only their own.
    """
    return character_feature_service.get_features(character_id, current_user)


@router.post(
    "/",
    response_model=CharacterFeatureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a feature on a character",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character or feature exists with the given ID."},
        409: {"description": "The character already has this feature."},
    },
)
def add_character_feature(
    character_id: int,
    data: CharacterFeatureAdd,
    character_feature_service: CharacterFeatureServiceDep,
    current_user: CurrentUserDep,
):
    """
    Record a reference feature on a character, with optional per-character
    notes (e.g. choices made within the feature). Rejects duplicates.
    """
    return character_feature_service.add_feature(character_id, data, current_user)


@router.patch(
    "/{character_feature_id}",
    response_model=CharacterFeatureResponse,
    summary="Change a feature grant's notes",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {
            "description": "No character exists with the given ID, or no feature grant exists with the given `character_feature_id`."
        },
    },
)
def update_character_feature(
    character_id: int,
    character_feature_id: int,
    data: CharacterFeatureUpdate,
    character_feature_service: CharacterFeatureServiceDep,
    current_user: CurrentUserDep,
):
    """
    Replace the notes on an already-recorded feature. Send `notes: ""` to
    clear them.
    """
    return character_feature_service.update_feature(character_id, character_feature_id, data, current_user)


@router.delete(
    "/{character_feature_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a feature from a character",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {
            "description": "No character exists with the given ID, or no feature grant exists with the given `character_feature_id`."
        },
    },
)
def remove_character_feature(
    character_id: int,
    character_feature_id: int,
    character_feature_service: CharacterFeatureServiceDep,
    current_user: CurrentUserDep,
):
    """
    Remove a feature grant from a character.
    """
    character_feature_service.remove_feature(character_id, character_feature_id, current_user)
    return None
