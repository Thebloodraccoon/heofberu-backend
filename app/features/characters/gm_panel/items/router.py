"""
GM-panel inventory endpoints: view (GM/owner) and manage (GM-only) a character's items.

The sub-router declares no prefix of its own; the panel's aggregating
router applies ``/{character_id}/gm-panel`` — combined, ``"/items"``
resolves to ``/characters/{character_id}/gm-panel/items``.
"""

from fastapi import APIRouter, status

from app.features.characters.gm_panel.dependencies import GmPanelItemsDep
from app.features.characters.gm_panel.items.schemas import (
    CharacterItemAdd,
    CharacterItemResponse,
    CharacterItemUpdate,
)
from app.features.users.security import CurrentUserDep, GmUserDep

router = APIRouter()


@router.get(
    "/items",
    response_model=list[CharacterItemResponse],
    summary="List a character's items",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_items(
    character_id: int,
    item_service: GmPanelItemsDep,
    current_user: CurrentUserDep,
):
    """

    List every item stack owned by a character. GM can view any
    character's items; players only their own.
    """

    return await item_service.get_items(character_id, current_user)


@router.post(
    "/items",
    response_model=CharacterItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an item stack to a character",
    responses={
        403: {"description": "You are not a GM."},
        404: {"description": "No character or item exists with the given ID."},
    },
)
async def add_character_item(
    character_id: int,
    data: CharacterItemAdd,
    item_service: GmPanelItemsDep,
    current_user: GmUserDep,
):
    """
    Add one item stack to a character's inventory. **GM only.**

    Each POST creates its own stack row — a character may own several
    stacks of the same item. `quantity` defaults to 1 (0 is allowed).
    """

    return await item_service.add_item(character_id, data, current_user)


@router.patch(
    "/items/{character_item_id}",
    response_model=CharacterItemResponse,
    summary="Update an item stack",
    responses={
        403: {"description": "You are not a GM."},
        404: {
            "description": "No character exists with the given ID, or no item stack exists with the given `character_item_id`."
        },
    },
)
async def update_character_item(
    character_id: int,
    character_item_id: int,
    data: CharacterItemUpdate,
    item_service: GmPanelItemsDep,
    current_user: GmUserDep,
):
    """
    Change an item stack's quantity, equip/attunement state, or notes.
    **GM only.** Only provided fields are changed; `item_id` itself is
    immutable — remove the stack and add a new one instead.
    """

    return await item_service.update_item(character_id, character_item_id, data, current_user)


@router.delete(
    "/items/{character_item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an item stack from a character",
    responses={
        403: {"description": "You are not a GM."},
        404: {
            "description": "No character exists with the given ID, or no item stack exists with the given `character_item_id`."
        },
    },
)
async def remove_character_item(
    character_id: int,
    character_item_id: int,
    item_service: GmPanelItemsDep,
    current_user: GmUserDep,
):
    """Remove one item stack from a character's inventory. **GM only.**"""

    await item_service.remove_item(character_id, character_item_id, current_user)
    return None
