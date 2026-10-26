"""Armor endpoints: create an armor or a shield, edit its stats."""

from typing import Annotated

from fastapi import APIRouter, Body, status

from app.features.auth.dependencies import GmUserDep
from app.features.items.armor.schemas import ArmorCreate, ArmorUpdate
from app.features.items.crud.schemas import ItemResponse
from app.features.items.dependencies import ArmorServiceDep

router = APIRouter()


@router.post(
    "/armor",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an armor or a shield",
    responses={409: {"description": "An item with this name already exists."}},
)
async def create_armor(
    data: Annotated[
        ArmorCreate,
        Body(
            openapi_examples={
                "chain_mail": {
                    "summary": "Chain mail",
                    "value": {
                        "name": "Chain Mail",
                        "weight": 55,
                        "cost_gold": 75,
                        "armor": {
                            "armor_category": "HEAVY",
                            "armor_class_base": 16,
                            "strength_requirement": 13,
                            "stealth_disadvantage": True,
                        },
                    },
                },
                "shield": {
                    "summary": "Shield (+2)",
                    "value": {"name": "Shield", "armor": {"armor_category": "SHIELD", "armor_class_base": 2}},
                },
            }
        ),
    ],
    service: ArmorServiceDep,
    _: GmUserDep,
):
    """
    Create an `ARMOR` item; `armor_category: SHIELD` makes it a shield (`armor_class_base` = its bonus).
    **GM only.**
    """

    return await service.create(data)


@router.patch(
    "/{item_id:int}/armor",
    response_model=ItemResponse,
    summary="Update an armor's stats",
    responses={
        404: {"description": "No item exists with the given ID."},
        409: {"description": "The item is not an armor."},
    },
)
async def update_armor(item_id: int, data: ArmorUpdate, service: ArmorServiceDep, _: GmUserDep):
    """Change only the stats sent. The core is `PATCH /items/{id}`. **GM only.**"""

    return await service.update_details(item_id, data)
