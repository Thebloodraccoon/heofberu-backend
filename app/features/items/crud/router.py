"""Item core endpoints: listing, detail, ``GEAR`` creation, core PATCH and delete."""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.constants import ArmorProficiency, GearType, ItemKind, ItemRarity, ToolCategory, WeaponProficiency
from app.core.pagination import Page
from app.features.auth.dependencies import FounderDep, GmUserDep
from app.features.items.crud.schemas import GearCreate, ItemCoreUpdate, ItemGetAllResponse, ItemResponse
from app.features.items.dependencies import ItemCrudDep

router = APIRouter()


@router.get(
    "",
    response_model=Page[ItemGetAllResponse],
    summary="List items",
)
async def get_items(
    item_service: ItemCrudDep,
    ids: list[int] | None = Query(None, alias="id", description="Any-of match on the item id (repeat the key)."),
    kind: list[ItemKind] | None = Query(
        None, description="Any-of match on the item's kind (repeat the key: `?kind=WEAPON&kind=ARMOR`)."
    ),
    subtype: list[GearType] | None = Query(None, description="Any-of match on what a GEAR item is (potion, ring…)."),
    rarity: list[ItemRarity] | None = Query(None, description="Any-of match on the item's rarity (repeat the key)."),
    magic: bool | None = Query(None, description="`true`: magic items (any rarity but NONE), `false`: mundane."),
    weapon_category: list[WeaponProficiency] | None = Query(None, description="Any-of match on a weapon's category."),
    armor_category: list[ArmorProficiency] | None = Query(
        None, description="Any-of match on an armor's category (`SHIELD` = shields)."
    ),
    tool_category: list[ToolCategory] | None = Query(None, description="Any-of match on a tool's category."),
    property_id: list[int] | None = Query(
        None, description="Weapons having ALL these weapon properties (repeat the key)."
    ),
    search: str | None = Query(
        None, max_length=100, description="Case-insensitive substring match against the item's name."
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
):
    """
    Return a paginated list of lightweight items, with filters and search.
    Open endpoint.
    """

    filters = {
        "id": ids,
        "kind": kind,
        "subtype": subtype,
        "rarity": rarity,
        "magic": magic,
        "weapon_category": weapon_category,
        "armor_category": armor_category,
        "tool_category": tool_category,
        "property_id": property_id,
    }
    return await item_service.get_all(page=page, size=size, filters=filters, search=search)


@router.get(
    "/{item_id:int}",
    response_model=ItemResponse,
    summary="Get an item by ID",
    responses={
        404: {"description": "Item with id not found."},
    },
)
async def get_item(item_id: int, item_service: ItemCrudDep):
    """
    Return a single item: the core, the detail record of its kind (`weapon` / `armor` / `tool`),
    weapon properties and the speed/AC effects it gives while equipped.
    Open endpoint.
    """

    return await item_service.get_by_id(item_id)


@router.post(
    "",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a gear item (not a weapon, armor or tool)",
    responses={
        409: {"description": "An item with this name already exists."},
    },
)
async def create_item(
    data: Annotated[
        GearCreate,
        Body(
            openapi_examples={
                "magic_item": {
                    "summary": "Wondrous item requiring attunement",
                    "value": {
                        "name": "Cloak of Protection",
                        "subtype": "WONDROUS_ITEM",
                        "rarity": "UNCOMMON",
                        "requires_attunement": True,
                        "weight": 1,
                        "description": "You gain a +1 bonus to AC and saving throws while wearing this cloak.",
                    },
                },
                "gear": {
                    "summary": "Adventuring gear",
                    "value": {"name": "Rope, hempen (50 feet)", "subtype": "ADVENTURING_GEAR", "weight": 10},
                },
            },
        ),
    ],
    item_service: ItemCrudDep,
    _: GmUserDep,
):
    """
    Create a `GEAR` item — a potion, ring, wondrous item, gear, treasure… (`subtype`). Weapons, armor and
    tools have their own endpoints (`POST /items/weapons`, `/items/armor`, `/items/tools`). **GM only.**
    """

    return await item_service.create(data)


@router.patch(
    "/{item_id:int}",
    response_model=ItemResponse,
    summary="Update an item's core fields",
    responses={
        409: {"description": "Another item already uses the requested name."},
        404: {"description": "No item exists with the given ID."},
        422: {"description": "`subtype` sent for an item that isn't GEAR."},
    },
)
async def update_item(item_id: int, data: ItemCoreUpdate, item_service: ItemCrudDep, _: GmUserDep):
    """
    Partially update the core (name, rarity, attunement, weight, cost, magic bonus, description; `subtype` of
    a GEAR item). The kind is fixed; a weapon's/armor's/tool's stats are `PATCH /items/{id}/weapon|armor|tool`.
    **GM only.**
    """

    return await item_service.update(item_id, data)


@router.delete(
    "/{item_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an item",
    responses={
        404: {"description": "No item exists with the given ID."},
        409: {"description": "Item is still owned by a character or referenced by a class, background or feature."},
    },
)
async def delete_item(item_id: int, item_service: ItemCrudDep, _: FounderDep):
    """
    Delete an item, unless a character owns it or a class, background,
    feature effect or character proficiency still references it.
    **Founder only.**
    """

    await item_service.delete(item_id)
    return None
