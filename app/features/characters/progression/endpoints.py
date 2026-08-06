"""Endpoints for character progression: race/class change and leveling up."""

from fastapi import APIRouter

from app.core.dependencies import CharacterProgressionServiceDep, CharacterServiceDep, CurrentUserDep
from app.features.characters.progression.schemas import (
    CharacterASIChoiceResponse,
    ClassChange,
    LevelUpRequest,
    RaceChange,
)
from app.models.character_model import Character

router = APIRouter(tags=["Characters Progression"])


@router.patch(
    "/{character_id}/progression/race",
    summary="Change a character's race",
    description="Sets ``race_id`` (null clears it) and re-derives race ability bonuses.",
)
def change_race(
    character_id: int,
    data: RaceChange,
    progression_service: CharacterProgressionServiceDep,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
) -> Character:
    progression_service.change_race(character_id, data, current_user)
    return character_service.get_character(character_id, current_user)


@router.patch(
    "/{character_id}/progression/class",
    summary="Change a character's class",
    description="Replaces the class and re-applies spell slot progression for the current level.",
)
def change_class(
    character_id: int,
    data: ClassChange,
    progression_service: CharacterProgressionServiceDep,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
) -> Character:
    progression_service.change_class(character_id, data, current_user)
    return character_service.get_character(character_id, current_user)


@router.post(
    "/{character_id}/progression/level-up",
    summary="Level a character up",
    description=(
        "Advances the character one level. At ASI levels (4/8/12/16/19) a ``choice`` "
        "(ASI increments or a feat) is required and is recorded in ``character_asi_choices``."
    ),
)
def level_up(
    character_id: int,
    data: LevelUpRequest,
    progression_service: CharacterProgressionServiceDep,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
) -> Character:
    progression_service.level_up(character_id, data, current_user)
    return character_service.get_character(character_id, current_user)


@router.get(
    "/{character_id}/progression/asi-choices",
    summary="List a character's resolved ASI-level choices",
    description="Audit trail of every Ability Score Improvement resolution, ordered by level.",
    response_model=list[CharacterASIChoiceResponse],
)
def get_asi_choices(
    character_id: int,
    progression_service: CharacterProgressionServiceDep,
    current_user: CurrentUserDep,
) -> list[CharacterASIChoiceResponse]:
    return progression_service.get_asi_choices(character_id, current_user)
