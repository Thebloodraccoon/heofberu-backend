"""
GM max-level endpoints under ``/gm-panel/max-level``.

The sub-router declares no prefix of its own; the panel's aggregating
router applies ``/{character_id}/gm-panel``.
"""

from fastapi import APIRouter

from app.core.security.dependencies import CurrentUserDep, GmUserDep
from app.features.characters.gm_panel.dependencies import GmPanelLevelDep
from app.features.characters.gm_panel.level.schemas import CharacterMaxLevelResponse, MaxLevelUpdate

router = APIRouter()


@router.patch(
    "/max-level",
    response_model=CharacterMaxLevelResponse,
    summary="Raise a character's maximum allowed level",
    responses={
        400: {"description": "The new maximum is not above the stored one or below the character's level."},
        403: {"description": "You are not a GM."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def set_character_max_level(
    character_id: int,
    data: MaxLevelUpdate,
    level_service: GmPanelLevelDep,
    current_user: GmUserDep,
) -> CharacterMaxLevelResponse:
    """
    Raise the maximum level a character may reach (GM-only).

    The cap can only move up: a value at or below the currently stored
    maximum — or below the character's current level — is rejected.
    The character can then level up to it via the progression endpoint.
    """

    return await level_service.set_max_level(character_id, data, current_user)


@router.get(
    "/max-level",
    response_model=CharacterMaxLevelResponse,
    summary="Show a character's maximum allowed level",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_max_level(
    character_id: int,
    level_service: GmPanelLevelDep,
    current_user: CurrentUserDep,
) -> CharacterMaxLevelResponse:
    """
    Return the character's current level and the GM-set maximum it may
    reach (GM or owner).
    """

    return await level_service.get_max_level(character_id, current_user)
