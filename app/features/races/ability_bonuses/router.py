"""
Race ability-bonus endpoints: full replacement of a race's bonuses
(query-style ID — the race is identified by the required ``race_id``
query parameter).
"""

from typing import Annotated

from fastapi import APIRouter, Body

from app.features.races.dependencies import RaceAbilityBonusesDep
from app.features.races.schemas import AbilityBonusesUpdate, RaceResponse
from app.features.users.security import GmUserDep

router = APIRouter()


@router.put(
    "/{race_id:int}/ability-bonuses",
    response_model=RaceResponse,
    summary="Replace a race's ability bonuses",
    responses={
        404: {"description": "No race exists with the given ID."},
    },
)
async def set_ability_bonuses(
    race_id: int,
    data: Annotated[
        AbilityBonusesUpdate,
        Body(
            openapi_examples={
                "replace": {
                    "summary": "Replace with two bonuses",
                    "value": {"ability_bonuses": [{"ability": "DEX", "bonus": 2}, {"ability": "INT", "bonus": 1}]},
                },
                "clear": {
                    "summary": "Clear all bonuses",
                    "value": {"ability_bonuses": []},
                },
            },
        ),
    ],
    race_service: RaceAbilityBonusesDep,
    _: GmUserDep,
):
    """
    Replace all ability score bonuses for a race. **GM only.**

    Full replace, not merge: the list in the request body becomes the
    complete set of bonuses for this race — any bonus not included is
    removed. Send an empty list to clear all bonuses.
    """

    return await race_service.set_ability_bonuses(race_id, data)
