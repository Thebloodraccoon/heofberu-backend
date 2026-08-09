"""Character item endpoints: manage a character's inventory."""

from fastapi import APIRouter, status

from app.core.dependencies import CharacterItemServiceDep, CurrentUserDep
from app.features.characters.items.schemas import (
    CharacterItemAdd,
    CharacterItemResponse,
    CharacterItemUpdate,
)

router = APIRouter(tags=["Character Items"])


@router.get(
    "/{character_id}/items",
    response_model=list[CharacterItemResponse],
    summary="List a character's items",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_items(
    character_id: int,
    character_item_service: CharacterItemServiceDep,
    current_user: CurrentUserDep,
):
    """
    List every item stack owned by a character. GM can view any
    character's items; players only their own.
    """

    return await character_item_service.get_items(character_id, current_user)


@router.post(
    "/{character_id}/items",
    response_model=CharacterItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an item to a character",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character or item exists with the given ID."},
    },
)
async def add_character_item(
    character_id: int,
    data: CharacterItemAdd,
    character_item_service: CharacterItemServiceDep,
    current_user: CurrentUserDep,
):
    """
    Add a stack of an item to a character's inventory. Each POST creates
    its own stack row, so the same item can be owned multiple times.
    """

    return await character_item_service.add_item(character_id, data, current_user)


@router.patch(
    "/{character_id}/items/{character_item_id}",
    response_model=CharacterItemResponse,
    summary="Change an item stack",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {
            "description": "No character exists with the given ID, or no item stack exists with the given `character_item_id`."
        },
    },
)
async def update_character_item(
    character_id: int,
    character_item_id: int,
    data: CharacterItemUpdate,
    character_item_service: CharacterItemServiceDep,
    current_user: CurrentUserDep,
):
    """
    Change a stack's quantity, equip/attunement state, or notes. Only the
    fields sent in the body are updated.
    """
    return await character_item_service.update_item(character_id, character_item_id, data, current_user)


@router.delete(
    "/{character_id}/items/{character_item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an item from a character",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {
            "description": "No character exists with the given ID, or no item stack exists with the given `character_item_id`."
        },
    },
)
async def remove_character_item(
    character_id: int,
    character_item_id: int,
    character_item_service: CharacterItemServiceDep,
    current_user: CurrentUserDep,
):
    """Remove an item stack from a character's inventory."""

    await character_item_service.remove_item(character_id, character_item_id, current_user)
    return None
