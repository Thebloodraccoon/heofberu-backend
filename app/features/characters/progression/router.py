"""Endpoints for character progression: race/class/subclass/subrace change and leveling up."""

from fastapi import APIRouter

from app.core.security.dependencies import CurrentUserDep
from app.features.characters.dependencies import CharacterProgressionServiceDep, CharacterServiceDep
from app.features.characters.progression.schemas import (
    CharacterASIChoiceResponse,
    ClassChange,
    LevelUpRequest,
    RaceChange,
    SubclassChange,
    SubraceChange,
)
from app.features.characters.schemas import CharacterResponse

router = APIRouter(tags=["Characters Progression"])


@router.patch(
    "/{character_id}/progression/race",
    response_model=CharacterResponse,
    summary="Change a character's race",
    description="Sets ``race_id`` (null clears it) and re-derives race ability bonuses.",
)
async def change_race(
    character_id: int,
    data: RaceChange,
    progression_service: CharacterProgressionServiceDep,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
) -> CharacterResponse:
    await progression_service.change_race(character_id, data, current_user)
    return await character_service.get_character(character_id, current_user)


@router.patch(
    "/{character_id}/progression/class",
    response_model=CharacterResponse,
    summary="Change a character's class",
    description="Replaces the class and re-applies spell slot progression for the current level.",
)
async def change_class(
    character_id: int,
    data: ClassChange,
    progression_service: CharacterProgressionServiceDep,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
) -> CharacterResponse:
    await progression_service.change_class(character_id, data, current_user)
    return await character_service.get_character(character_id, current_user)


@router.patch(
    "/{character_id}/progression/subclass",
    response_model=CharacterResponse,
    summary="Set or clear a character's subclass",
    description=(
        "Sets ``subclass_id`` (must belong to the character's class; null clears it). "
        "Grants the subclass's features at or below the character's current level."
    ),
)
async def change_subclass(
    character_id: int,
    data: SubclassChange,
    progression_service: CharacterProgressionServiceDep,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
) -> CharacterResponse:
    await progression_service.set_subclass(character_id, data, current_user)
    return await character_service.get_character(character_id, current_user)


@router.patch(
    "/{character_id}/progression/subrace",
    response_model=CharacterResponse,
    summary="Set or clear a character's subrace",
    description=(
        "Sets ``subrace_id`` (must belong to the character's race; null clears it). "
        "Grants the subrace's features at or below the character's current level "
        "and re-derives subrace ability bonuses."
    ),
)
async def change_subrace(
    character_id: int,
    data: SubraceChange,
    progression_service: CharacterProgressionServiceDep,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
) -> CharacterResponse:
    await progression_service.set_subrace(character_id, data, current_user)
    return await character_service.get_character(character_id, current_user)


@router.post(
    "/{character_id}/progression/level-up",
    response_model=CharacterResponse,
    summary="Level a character up",
    description=(
        "Advances the character one level. At ASI levels (4/8/12/16/19) a ``choice`` "
        "(ASI increments or a feat) is required and is recorded in ``character_asi_choices``."
    ),
)
async def level_up(
    character_id: int,
    data: LevelUpRequest,
    progression_service: CharacterProgressionServiceDep,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
) -> CharacterResponse:
    await progression_service.level_up(character_id, data, current_user)
    return await character_service.get_character(character_id, current_user)


@router.get(
    "/{character_id}/progression/asi-choices",
    summary="List a character's resolved ASI-level choices",
    description="Audit trail of every Ability Score Improvement resolution, ordered by level.",
    response_model=list[CharacterASIChoiceResponse],
)
async def get_asi_choices(
    character_id: int,
    progression_service: CharacterProgressionServiceDep,
    current_user: CurrentUserDep,
) -> list[CharacterASIChoiceResponse]:
    return await progression_service.get_asi_choices(character_id, current_user)
