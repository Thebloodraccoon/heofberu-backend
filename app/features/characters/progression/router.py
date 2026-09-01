"""
Endpoints for character progression: subclass/subrace/background setup,
leveling up, rebuild (query-style IDs).

The router declares no prefix of its own;
``app.features.characters.router`` applies the ``/characters`` prefix —
combined, ``"/progression/..."`` resolves to
``/characters/progression/...?character_id=...``. The character is
identified by the required ``character_id`` query parameter.
"""

from typing import Annotated

from fastapi import APIRouter, Body

from app.features.characters.dependencies import CharacterProgressionServiceDep, CharacterServiceDep
from app.features.characters.progression.schemas import (
    BackgroundChange,
    CanLevelUpResponse,
    CharacterASIChoiceResponse,
    LevelUpRequest,
    SubclassChange,
    SubraceChange,
)
from app.features.characters.schemas import CharacterResponse
from app.features.users.security import CurrentUserDep

router = APIRouter()


@router.patch(
    "/{character_id:int}/progression/background",
    response_model=CharacterResponse,
    summary="Set a character's background (only while it has none)",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "Character or background not found."},
        409: {"description": "The character already has a background."},
    },
)
async def set_background(
    character_id: int,
    data: Annotated[
        BackgroundChange,
        Body(
            openapi_examples={
                "set": {
                    "summary": "Set the soldier background",
                    "value": {"background_id": 3},
                },
            }
        ),
    ],
    progression_service: CharacterProgressionServiceDep,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """
    Set a character's background — only allowed while the character has
    none (a background picked at creation can never be swapped). Grants
    everything a background grants at creation: its features, its granted
    skills, and its starting equipment.
    """

    await progression_service.set_background(character_id, data, current_user)
    return await character_service.get_character(character_id, current_user)


@router.patch(
    "/{character_id:int}/progression/subclass",
    response_model=CharacterResponse,
    summary="Set or clear a character's subclass",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "Character not found, or the subclass does not belong to the character's class."},
    },
)
async def change_subclass(
    character_id: int,
    data: Annotated[
        SubclassChange,
        Body(
            openapi_examples={
                "set": {
                    "summary": "Pick the champion subclass",
                    "value": {"subclass_id": 7},
                },
                "clear": {
                    "summary": "Clear the current subclass",
                    "value": {"subclass_id": None},
                },
            }
        ),
    ],
    progression_service: CharacterProgressionServiceDep,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """
    Sets ``subclass_id`` (must belong to the character's class; null
    clears it). Grants the subclass's features at or below the
    character's current level.
    """

    await progression_service.set_subclass(character_id, data, current_user)
    return await character_service.get_character(character_id, current_user)


@router.patch(
    "/{character_id:int}/progression/subrace",
    response_model=CharacterResponse,
    summary="Set or clear a character's subrace",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "Character not found, or the subrace does not belong to the character's race."},
    },
)
async def change_subrace(
    character_id: int,
    data: Annotated[
        SubraceChange,
        Body(
            openapi_examples={
                "set": {
                    "summary": "Pick the hill dwarf subrace",
                    "value": {"subrace_id": 2},
                },
                "clear": {
                    "summary": "Clear the current subrace",
                    "value": {"subrace_id": None},
                },
            }
        ),
    ],
    progression_service: CharacterProgressionServiceDep,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """
    Sets ``subrace_id`` (must belong to the character's race; null clears
    it). Grants the subrace's features at or below the character's
    current level and re-derives subrace ability bonuses.
    """

    await progression_service.set_subrace(character_id, data, current_user)
    return await character_service.get_character(character_id, current_user)


@router.post(
    "/{character_id:int}/rebuild",
    response_model=CharacterResponse,
    summary="Point-rebuild a character (not implemented yet)",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "Character not found."},
        501: {"description": "Rebuild is planned but not implemented yet."},
    },
)
async def rebuild_character(
    character_id: int,
    progression_service: CharacterProgressionServiceDep,
    current_user: CurrentUserDep,
):
    """
    Placeholder for the future point-rebuild: a full class/race swap that
    resets every derived choice while keeping the character row. Currently
    always responds with **501 Not Implemented**.
    """

    await progression_service.request_rebuild(character_id, current_user)


@router.post(
    "/{character_id:int}/progression/level-up",
    response_model=CharacterResponse,
    summary="Level a character up",
    responses={
        400: {
            "description": (
                "The character is already at the maximum level, an ASI choice is "
                "required but missing (or given on a non-ASI level), the hit-point gain "
                "is out of range, or an ASI choice exceeds the ability-score cap."
            )
        },
        403: {"description": "You do not have access to this character."},
        404: {"description": "Character or feat not found."},
        409: {"description": "The character already has the feat chosen by the ASI option."},
    },
)
async def level_up(
    character_id: int,
    data: Annotated[
        LevelUpRequest,
        Body(
            openapi_examples={
                "plain": {
                    "summary": "Level up taking the average hit-point roll, no ASI level",
                    "value": {},
                },
                "asi-choice": {
                    "summary": "Level up at an ASI level with a +2 STR improvement",
                    "value": {
                        "hit_points_gained": 9,
                        "choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 2}]},
                    },
                },
                "feat-choice": {
                    "summary": "Level up taking a feat instead of the ASI",
                    "value": {"choice": {"type": "FEAT", "feat_id": 12}},
                },
            }
        ),
    ],
    progression_service: CharacterProgressionServiceDep,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """
    Advances the character one level. At ASI levels (4/8/12/16/19) a
    ``choice`` (ASI increments or a feat) is required and is recorded in
    ``character_asi_choices``.
    """

    await progression_service.level_up(character_id, data, current_user)
    return await character_service.get_character(character_id, current_user)


@router.get(
    "/{character_id:int}/progression/can-level-up",
    response_model=CanLevelUpResponse,
    summary="Check whether a character can level up",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def can_level_up(
    character_id: int,
    progression_service: CharacterProgressionServiceDep,
    current_user: CurrentUserDep,
):
    """
    Returns whether the character's level is below the GM-set maximum
    (``character_max_levels``), along with both values.
    """

    return await progression_service.can_level_up(character_id, current_user)


@router.get(
    "/{character_id:int}/progression/asi-choices",
    response_model=list[CharacterASIChoiceResponse],
    summary="List a character's resolved ASI-level choices",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_asi_choices(
    character_id: int,
    progression_service: CharacterProgressionServiceDep,
    current_user: CurrentUserDep,
):
    """Audit trail of every Ability Score Improvement resolution, ordered by level."""

    return await progression_service.get_asi_choices(character_id, current_user)
