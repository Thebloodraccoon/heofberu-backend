"""
GM-panel inventory endpoints: manage a character's items (writes, GM-only;
query-style IDs).

The sub-router declares no prefix of its own; the panel's aggregating
router applies ``/gm-panel`` — combined, ``"/items"`` resolves to
``/characters/gm-panel/items?character_id=...``. The character is
identified by the required ``character_id`` query parameter; stack
edits/removals additionally take ``item_id`` (the character-item stack
row ID). Reads are served by the player-facing
``GET /characters/{character_id}/items`` (see ``crud/``).
"""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.features.characters.gm_panel.dependencies import GmPanelItemsDep
from app.features.characters.gm_panel.items.schemas import CharacterItemAdd, CharacterItemUpdate
from app.features.characters.schemas import CharacterItemResponse
from app.features.users.security import GmUserDep

router = APIRouter()


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
    data: Annotated[
        CharacterItemAdd,
        Body(
            openapi_examples={
                "equipped": {
                    "summary": "Add and equip a longsword",
                    "value": {"item_id": 4, "quantity": 1, "is_equipped": True},
                },
                "consumable-stack": {
                    "summary": "Add a stack of ten healing potions with a note",
                    "value": {"item_id": 17, "quantity": 10, "notes": "Bought in Harrowdale."},
                },
            }
        ),
    ],
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
    "/items",
    response_model=CharacterItemResponse,
    summary="Update an item stack",
    responses={
        403: {"description": "You are not a GM."},
        404: {
            "description": "No character exists with the given ID, or no item stack exists with the given `item_id`."
        },
    },
)
async def update_character_item(
    character_id: int,
    item_id: Annotated[int, Query(gt=0)],
    data: Annotated[
        CharacterItemUpdate,
        Body(
            openapi_examples={
                "equip-and-attune": {
                    "summary": "Equip and attune the item",
                    "value": {"is_equipped": True, "is_attuned": True},
                },
                "quantity": {
                    "summary": "Spend five arrows from the stack",
                    "value": {"quantity": 15},
                },
            }
        ),
    ],
    item_service: GmPanelItemsDep,
    current_user: GmUserDep,
):
    """
    Change an item stack's quantity, equip/attunement state, or notes.
    **GM only.** Only provided fields are changed; the referenced item
    itself is immutable — remove the stack and add a new one instead.
    """

    return await item_service.update_item(character_id, item_id, data, current_user)


@router.delete(
    "/items",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an item stack from a character",
    responses={
        403: {"description": "You are not a GM."},
        404: {
            "description": "No character exists with the given ID, or no item stack exists with the given `item_id`."
        },
    },
)
async def remove_character_item(
    character_id: int,
    item_id: Annotated[int, Query(gt=0)],
    item_service: GmPanelItemsDep,
    current_user: GmUserDep,
):
    """Remove one item stack from a character's inventory. **GM only.**"""

    await item_service.remove_item(character_id, item_id, current_user)
    return None
