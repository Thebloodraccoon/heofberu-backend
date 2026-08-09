"""Item endpoints: listing and CRUD."""

from fastapi import APIRouter, Body, Query

from app.constants import ItemRarity, ItemType
from app.core.base_service import Page
from app.core.dependencies import FounderDep, GmUserDep, ItemServiceDep
from app.features.items.schemas import ItemCreate, ItemGetAllResponse, ItemResponse, ItemUpdate

router = APIRouter(prefix="/items", tags=["Items"])


@router.get(
    "",
    response_model=Page[ItemGetAllResponse],
    summary="List items",
)
async def get_items(
    item_service: ItemServiceDep,
    item_type: ItemType | None = None,
    rarity: ItemRarity | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
):
    """
    Return a paginated list of items with only `id`, `name`, `item_type`,
    `rarity`, `cost_gold`, and `is_homebrew`.

    Open endpoint, no authentication required.

    `item_type`/`rarity` are exact matches on
    their enums (invalid values → `422`, and `/docs` shows them as dropdowns).
    `search` is a case-insensitive partial match against the item name.
    All can be combined.

    Response is `{items, total, page, size}` — `total` is the count of
    matching items across every page, not just this one.

    Does not include weapon/armor detail fields or description — use
    `GET /items/{item_id}` for the full record.
    """

    filters = {"item_type": item_type, "rarity": rarity}
    return await item_service.get_all(page=page, size=size, filters=filters, search=search)


@router.get(
    "/{item_id}",
    response_model=ItemResponse,
    summary="Get an item by ID",
    responses={
        404: {"description": "Item with id not found."},
    },
)
async def get_item(item_id: int, item_service: ItemServiceDep):
    """
    Return a single item by ID, with full detail.

    Open endpoint, no authentication required.
    """

    return await item_service.get_by_id(item_id)


@router.post(
    "",
    response_model=ItemResponse,
    status_code=201,
    summary="Create an item",
    responses={
        409: {"description": "An item with this name already exists."},
    },
)
async def create_item(
    item_service: ItemServiceDep,
    current_user: GmUserDep,
    item_data: ItemCreate = Body(
        openapi_examples={
            "weapon": {
                "summary": "Weapon",
                "value": {
                    "name": "Longsword",
                    "item_type": "WEAPON",
                    "rarity": "NONE",
                    "weight": 3,
                    "cost_gold": 15,
                    "damage_dice_count": 1,
                    "damage_dice_type": "D8",
                    "damage_type": "SLASHING",
                    "weapon_properties": "VERSATILE",
                    "description": "A versatile martial melee weapon.",
                },
            },
            "armor": {
                "summary": "Armor",
                "value": {
                    "name": "Chain Mail",
                    "item_type": "ARMOR",
                    "rarity": "NONE",
                    "weight": 55,
                    "cost_gold": 75,
                    "armor_class_base": 16,
                    "armor_class_dex_bonus": False,
                    "strength_requirement": 13,
                    "stealth_disadvantage": True,
                    "description": "Made of interlocking metal rings, chain mail includes a layer of quilted fabric worn underneath to prevent chafing.",
                },
            },
            "magic_item": {
                "summary": "Magic item requiring attunement",
                "value": {
                    "name": "Cloak of Protection",
                    "item_type": "WONDROUS_ITEM",
                    "rarity": "UNCOMMON",
                    "requires_attunement": True,
                    "weight": 1,
                    "description": "You gain a +1 bonus to AC and saving throws while wearing this cloak.",
                },
            },
        },
    ),
):
    """Create a new item. **GM only.**"""

    return await item_service.create_item(item_data, created_by_id=current_user.id)


@router.patch(
    "/{item_id}",
    response_model=ItemResponse,
    summary="Update an item",
    responses={
        404: {"description": "No item exists with the given ID."},
        409: {"description": "Another item already uses the requested name."},
    },
)
async def update_item(item_id: int, update_data: ItemUpdate, item_service: ItemServiceDep, _: GmUserDep):
    """
    Partially update an item. **GM only.**

    Only fields included in the request body are changed; omitted fields
    are left as-is.
    """

    return await item_service.update(item_id, update_data)


@router.delete(
    "/{item_id}",
    status_code=204,
    summary="Delete an item",
    responses={
        404: {"description": "No item exists with the given ID."},
        409: {"description": "Item is still owned by one or more characters."},
    },
)
async def delete_item(item_id: int, item_service: ItemServiceDep, _: FounderDep):
    """
    Delete an item. **Found-father only.**

    Blocked if the item is still owned by one or more characters (the
    service raises ``RecordInUseError``, mapped to a 409 by the global
    exception handler).
    """

    await item_service.delete(item_id)
    return None
