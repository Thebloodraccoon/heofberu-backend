"""Character condition endpoints: manage active conditions on a character."""

from fastapi import APIRouter, status

from app.constants import ConditionType
from app.features.characters.conditions.schemas import (
    CharacterConditionAdd,
    CharacterConditionResponse,
    CharacterConditionUpdate,
)
from app.features.characters.dependencies import CharacterConditionServiceDep
from app.features.users.security import CurrentUserDep

router = APIRouter(prefix="/{character_id}/conditions", tags=["Character Conditions"])


@router.get(
    "",
    response_model=list[CharacterConditionResponse],
    summary="List a character's conditions",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_conditions(
    character_id: int,
    character_condition_service: CharacterConditionServiceDep,
    current_user: CurrentUserDep,
):
    """
    List every condition a character is currently under. GM can view any
    character's conditions; players only their own.
    """

    return await character_condition_service.get_conditions(character_id, current_user)


@router.post(
    "",
    response_model=CharacterConditionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a condition on a character",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
        409: {"description": "The character is already under this condition."},
    },
)
async def add_character_condition(
    character_id: int,
    data: CharacterConditionAdd,
    character_condition_service: CharacterConditionServiceDep,
    current_user: CurrentUserDep,
):
    """
    Record an active condition on a character. EXHAUSTION requires
    ``exhaustion_level`` (1-6); other conditions reject it. Rejects
    duplicates — a condition is either active or not.
    """

    return await character_condition_service.add_condition(character_id, data, current_user)


@router.patch(
    "/{condition}",
    response_model=CharacterConditionResponse,
    summary="Change a condition's exhaustion level or source",
    responses={
        400: {"description": "Invalid `exhaustion_level` for this condition."},
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID, or the character is not under this condition."},
    },
)
async def update_character_condition(
    character_id: int,
    condition: ConditionType,
    data: CharacterConditionUpdate,
    character_condition_service: CharacterConditionServiceDep,
    current_user: CurrentUserDep,
):
    """
    Change a condition's ``exhaustion_level`` or ``source``. The
    condition itself is fixed by the URL path — remove it and re-add if
    the effect changes.
    """

    return await character_condition_service.update_condition(character_id, condition, data, current_user)


@router.delete(
    "/{condition}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a condition from a character",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID, or the character is not under this condition."},
    },
)
async def remove_character_condition(
    character_id: int,
    condition: ConditionType,
    character_condition_service: CharacterConditionServiceDep,
    current_user: CurrentUserDep,
):
    """Remove an active condition from a character."""

    await character_condition_service.remove_condition(character_id, condition, current_user)
    return None
