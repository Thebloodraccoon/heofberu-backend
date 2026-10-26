"""Weapon endpoints: create a weapon, edit its stats and properties."""

from typing import Annotated

from fastapi import APIRouter, Body, status

from app.features.auth.dependencies import GmUserDep
from app.features.items.crud.schemas import ItemResponse
from app.features.items.dependencies import WeaponServiceDep
from app.features.items.weapons.schemas import WeaponCreate, WeaponUpdate

router = APIRouter()


@router.post(
    "/weapons",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a weapon",
    responses={
        400: {"description": "Unknown weapon property id(s)."},
        409: {"description": "An item with this name already exists."},
        422: {"description": "Stats that don't fit together, or a property's required field missing."},
    },
)
async def create_weapon(
    data: Annotated[
        WeaponCreate,
        Body(
            openapi_examples={
                "longsword": {
                    "summary": "Longsword (versatile)",
                    "value": {
                        "name": "Longsword",
                        "weight": 3,
                        "cost_gold": 15,
                        "weapon": {
                            "weapon_category": "MARTIAL",
                            "attack_type": "MELEE_ATTACK",
                            "damage_dice_count": 1,
                            "damage_dice_type": "D8",
                            "damage_type": "SLASHING",
                            "versatile_dice_count": 1,
                            "versatile_dice_type": "D10",
                        },
                        "property_ids": [9],
                    },
                },
            }
        ),
    ],
    service: WeaponServiceDep,
    _: GmUserDep,
):
    """
    Create a `WEAPON` item: the core fields, its stats (`weapon`) and properties (`property_ids`, see
    `GET /items/properties`). A Thrown/Ammunition weapon needs `range_normal`, a Versatile one its two-handed
    damage. **GM only.**
    """

    return await service.create(data)


@router.patch(
    "/{item_id:int}/weapon",
    response_model=ItemResponse,
    summary="Update a weapon's stats and properties",
    responses={
        400: {"description": "Unknown weapon property id(s)."},
        404: {"description": "No item exists with the given ID."},
        409: {"description": "The item is not a weapon."},
        422: {"description": "Stats that don't fit together, or a property's required field missing."},
    },
)
async def update_weapon(item_id: int, data: WeaponUpdate, service: WeaponServiceDep, _: GmUserDep):
    """
    Change only the stats sent; `property_ids` replaces the whole list. The core is `PATCH /items/{id}`.
    **GM only.**
    """

    return await service.update_details(item_id, data)
