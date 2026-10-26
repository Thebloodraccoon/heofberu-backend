"""Item effect endpoints: the speed/AC effects an item gives while equipped."""

from typing import Annotated

from fastapi import APIRouter, Body

from app.features.auth.dependencies import GmUserDep
from app.features.features.effects.schemas import ItemEffectsUpdate, ItemEffectType
from app.features.items.dependencies import ItemEffectsDep
from app.features.items.effects.schemas import ItemEffectsResponse

router = APIRouter()


@router.get("/{item_id:int}/effects", response_model=ItemEffectsResponse, summary="Get an item's effects")
async def get_item_effects(item_id: int, service: ItemEffectsDep):
    """The speed and AC effects the item gives while a character has it equipped. Open endpoint."""

    return await service.get_effects(item_id)


@router.post(
    "/{item_id:int}/effects",
    response_model=ItemEffectsResponse,
    summary="Add effects to an item",
    responses={404: {"description": "No such item."}, 422: {"description": "Invalid or duplicate effect."}},
)
async def add_item_effects(
    item_id: int,
    data: Annotated[
        ItemEffectsUpdate,
        Body(
            openapi_examples={
                "ring_of_protection": {
                    "summary": "Ring of Protection: +1 AC",
                    "value": {"static_groups": [{"effect_type": "armor_class", "items": [{"value": 1}]}]},
                },
                "winged_boots": {
                    "summary": "Winged Boots: fly speed equal to walking",
                    "value": {
                        "static_groups": [
                            {"effect_type": "speed", "items": [{"speed_type": "FLY", "mode": "EQUAL_TO_WALK"}]}
                        ]
                    },
                },
            }
        ),
    ],
    service: ItemEffectsDep,
    _: GmUserDep,
):
    """
    Add speed / armor_class effects (the same `static_groups` shape as a feature's fixed effects). They apply
    while the item is equipped, and attuned too when it requires attunement. **GM only.**
    """

    return await service.add_effects(item_id, data)


@router.delete(
    "/{item_id:int}/effects/{effect_type}/{effect_id:int}",
    response_model=ItemEffectsResponse,
    summary="Remove an item effect",
    responses={404: {"description": "No such item or effect."}},
)
async def remove_item_effect(
    item_id: int, effect_type: ItemEffectType, effect_id: int, service: ItemEffectsDep, _: GmUserDep
):
    """Delete one effect row of the item. **GM only.**"""

    return await service.remove_effect(item_id, effect_type, effect_id)
