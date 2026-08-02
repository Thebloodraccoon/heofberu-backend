from fastapi import APIRouter, status

from app.core.dependencies import CharacterFeatServiceDep, CurrentUserDep
from app.features.characters.feats.schemas import (
    CharacterFeatAdd,
    CharacterFeatResponse,
    CharacterFeatUpdate,
)

router = APIRouter(prefix="/{character_id}/feats", tags=["Character Feats"])


@router.get(
    "/",
    response_model=list[CharacterFeatResponse],
    summary="List a character's feats",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
def get_character_feats(
    character_id: int,
    character_feat_service: CharacterFeatServiceDep,
    current_user: CurrentUserDep,
):
    """
    List every feat granted to a character. GM can view any character's
    feats; players only their own.
    """
    return character_feat_service.get_feats(character_id, current_user)


@router.post(
    "/",
    response_model=CharacterFeatResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Grant a feat to a character",
    responses={
        400: {
            "description": (
                "`ability_score_increase_id` doesn't belong to this feat, or the "
                "character doesn't meet the feat's ability-score prerequisite."
            )
        },
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character or feat exists with the given ID."},
        409: {"description": "The character already has this feat."},
    },
)
def add_character_feat(
    character_id: int,
    data: CharacterFeatAdd,
    character_feat_service: CharacterFeatServiceDep,
    current_user: CurrentUserDep,
):
    """
    Grant a feat to a character.

    Validates, in order: the feat exists; the character doesn't already
    have it (duplicates are rejected); if `ability_score_increase_id` is
    given, it belongs to this specific feat; and, if the feat has an
    ability-score prerequisite, the character's current *effective* score
    meets it.

    Character level is intentionally not checked — 5e ties feats to ASI
    opportunities at specific class levels, but there's no single
    universal rule across every class/variant, so that's left to GM/player
    judgment.

    Recalculates and persists the character's effective-ability-score
    cache before returning, since a feat's ASI choice can change it.
    """
    return character_feat_service.add_feat(character_id, data, current_user)


@router.patch(
    "/{character_feat_id}",
    response_model=CharacterFeatResponse,
    summary="Change a feat grant's ability score increase choice",
    responses={
        400: {"description": "`ability_score_increase_id` doesn't belong to this feat."},
        403: {"description": "You do not have access to this character."},
        404: {
            "description": "No character exists with the given ID, or no feat grant exists with the given `character_feat_id`."
        },
    },
)
def update_character_feat(
    character_id: int,
    character_feat_id: int,
    data: CharacterFeatUpdate,
    character_feat_service: CharacterFeatServiceDep,
    current_user: CurrentUserDep,
):
    """
    Change or clear the ASI choice for an already-granted feat. Send
    `ability_score_increase_id: null` to clear it.

    Recalculates and persists the character's effective-ability-score
    cache before returning.
    """
    return character_feat_service.update_feat(character_id, character_feat_id, data, current_user)


@router.delete(
    "/{character_feat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a feat from a character",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {
            "description": "No character exists with the given ID, or no feat grant exists with the given `character_feat_id`."
        },
    },
)
def remove_character_feat(
    character_id: int,
    character_feat_id: int,
    character_feat_service: CharacterFeatServiceDep,
    current_user: CurrentUserDep,
):
    """
    Revoke a feat from a character.

    Recalculates and persists the character's effective-ability-score
    cache before returning, since losing a feat's ASI can change it.
    """
    character_feat_service.remove_feat(character_id, character_feat_id, current_user)
    return None
