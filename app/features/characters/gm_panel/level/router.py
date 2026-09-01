"""GM max-level endpoints under ``/gm-panel/max-level`` (query-style ID)."""

from typing import Annotated

from fastapi import APIRouter, Body, Query

from app.features.characters.gm_panel.dependencies import GmPanelLevelDep
from app.features.characters.gm_panel.level.schemas import CharacterMaxLevelResponse, MaxLevelUpdate
from app.features.users.security import CurrentUserDep, GmUserDep

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
    data: Annotated[
        MaxLevelUpdate,
        Body(
            openapi_examples={
                "raise": {
                    "summary": "Raise the cap to level 10",
                    "value": {"max_level": 10},
                },
            }
        ),
    ],
    level_service: GmPanelLevelDep,
    current_user: GmUserDep,
):
    """
    Raise the maximum level a character may reach; it can only move up
    (never below the stored cap or current level). **GM only.**
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
):
    """
    Return the character's current level and the GM-set maximum it may
    reach (GM or owner).
    """

    return await level_service.get_max_level(character_id, current_user)
