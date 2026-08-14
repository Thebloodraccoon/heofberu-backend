"""Character proficiency endpoints (skills and saving throws)."""

from fastapi import APIRouter, Body

from app.core.security.dependencies import CurrentUserDep
from app.features.characters.dependencies import CharacterProficiencyServiceDep
from app.features.characters.proficiencies.schemas import (
    SavingThrowProficienciesUpdate,
    SkillProficienciesUpdate,
)
from app.features.characters.schemas import CharacterResponse

router = APIRouter(tags=["Characters Proficiencies"])


@router.put(
    "/{character_id}/skills",
    response_model=CharacterResponse,
    summary="Replace a character's skill proficiencies",
    responses={
        400: {"description": "One or more `skill_id`s don't correspond to an existing skill."},
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def set_character_skill_proficiencies(
    character_id: int,
    proficiency_service: CharacterProficiencyServiceDep,
    current_user: CurrentUserDep,
    data: SkillProficienciesUpdate = Body(
        openapi_examples={
            "replace": {
                "summary": "Replace with two proficiencies (one with expertise)",
                "value": {
                    "skill_proficiencies": [
                        {"skill_id": 3, "is_expertise": False},
                        {"skill_id": 7, "is_expertise": True},
                    ]
                },
            },
            "clear": {
                "summary": "Clear all skill proficiencies",
                "value": {"skill_proficiencies": []},
            },
        },
    ),
):
    """
    Fully replace a character's skill proficiencies (with expertise flags).

    Full replace, not merge: the list in the request body becomes the
    complete set of skill proficiencies for this character — any
    proficiency not included is removed. Send an empty list to clear all
    skill proficiencies.
    """

    return await proficiency_service.set_skill_proficiencies(character_id, data, current_user)


@router.put(
    "/{character_id}/saving-throws",
    response_model=CharacterResponse,
    summary="Replace a character's saving throw proficiencies",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def set_character_saving_throws(
    character_id: int,
    proficiency_service: CharacterProficiencyServiceDep,
    current_user: CurrentUserDep,
    data: SavingThrowProficienciesUpdate = Body(
        openapi_examples={
            "replace": {
                "summary": "Replace with two proficiencies",
                "value": {"saving_throws": ["STR", "CON"]},
            },
            "clear": {
                "summary": "Clear all saving throw proficiencies",
                "value": {"saving_throws": []},
            },
        },
    ),
):
    """
    Fully replace a character's saving throw proficiencies.

    Full replace, not merge: the `saving_throws` list in the request body
    becomes the complete set of saving throw proficiencies for this
    character — any ability not included is removed. Send an empty list
    to clear all saving throw proficiencies.
    """

    return await proficiency_service.set_saving_throw_proficiencies(character_id, data, current_user)
