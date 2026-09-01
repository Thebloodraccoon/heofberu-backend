"""Subrace ability-bonus endpoints: full replacement of a subrace's bonuses."""

from typing import Annotated

from fastapi import APIRouter, Body, Query

from app.features.subraces.crud.schemas import SubraceAbilityBonusesUpdate, SubraceResponse
from app.features.subraces.dependencies import SubraceAbilityBonusesDep
from app.features.users.security import GmUserDep

router = APIRouter()


@router.put(
    "/{subrace_id:int}/ability-bonuses",
    response_model=SubraceResponse,
    summary="Replace a subrace's ability bonuses",
    responses={404: {"description": "No subrace exists with the given ID under this race."}},
)
async def set_ability_bonuses(
    subrace_id: int,
    data: Annotated[
        SubraceAbilityBonusesUpdate,
        Body(
            openapi_examples={
                "replace": {
                    "summary": "Replace with one bonus",
                    "value": {"ability_bonuses": [{"ability": "WIS", "bonus": 1}]},
                },
                "clear": {
                    "summary": "Clear all bonuses",
                    "value": {"ability_bonuses": []},
                },
            },
        ),
    ],
    race_service: SubraceAbilityBonusesDep,
    _: GmUserDep,
):
    """Replace all ability score bonuses for a subrace. **GM only.**"""

    return await race_service.set_ability_bonuses(subrace_id, data)
