"""Character backstory endpoints: get/set a character's backstory via dedicated, uncached endpoints."""

from typing import Annotated

from fastapi import APIRouter, Body

from app.features.characters.backstory.schemas import (
    CharacterBackstoryResponse,
    CharacterBackstoryUpdate,
)
from app.features.characters.dependencies import CharacterBackstoryServiceDep
from app.features.users.security import CurrentUserDep

router = APIRouter()


@router.get(
    "/{character_id:int}/backstory",
    response_model=CharacterBackstoryResponse,
    summary="Get a character's backstory",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_backstory(
    character_id: int,
    character_backstory_service: CharacterBackstoryServiceDep,
    current_user: CurrentUserDep,
):
    """
    Return a character's backstory, served from the DB uncached (separate
    from the cached character sheet).

    GM can view any character's backstory; players only their own.
    """

    return await character_backstory_service.get_backstory(character_id, current_user)


@router.put(
    "/{character_id:int}/backstory",
    response_model=CharacterBackstoryResponse,
    summary="Set a character's backstory",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
        422: {"description": "`content` exceeds the 12000-character limit."},
    },
)
async def set_character_backstory(
    character_id: int,
    data: Annotated[
        CharacterBackstoryUpdate,
        Body(
            openapi_examples={
                "set": {
                    "summary": "Write a backstory for a fresh character",
                    "value": {
                        "content": "Born a blacksmith's apprentice, Elyse left the forge "
                        "after discovering a talent for arcane words she could not explain."
                    },
                },
                "rewrite": {
                    "summary": "Replace an existing backstory",
                    "value": {"content": "A rewritten, expanded version of the character's history."},
                },
            }
        ),
    ],
    character_backstory_service: CharacterBackstoryServiceDep,
    current_user: CurrentUserDep,
):
    """
    Set or replace a character's backstory (upsert — the row is created on
    first write). `content` is limited to 12000 characters.
    """

    return await character_backstory_service.set_backstory(character_id, data, current_user)
