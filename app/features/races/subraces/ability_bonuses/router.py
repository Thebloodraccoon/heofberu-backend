"""Subrace ability-bonus endpoints: full replacement of a subrace's bonuses."""

from fastapi import APIRouter, Body

from app.core.security.dependencies import GmUserDep
from app.features.races.subraces.crud.schemas import SubraceAbilityBonusesUpdate, SubraceResponse
from app.features.races.subraces.dependencies import SubraceAbilityBonusesDep

router = APIRouter()


@router.put(
    "/{subrace_id}/ability-bonuses",
    response_model=SubraceResponse,
    summary="Replace a subrace's ability bonuses",
    responses={404: {"description": "No subrace exists with the given ID under this race."}},
)
async def set_ability_bonuses(
    race_id: int,
    subrace_id: int,
    race_service: SubraceAbilityBonusesDep,
    _: GmUserDep,
    data: SubraceAbilityBonusesUpdate = Body(
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
):
    """
    Replace all ability score bonuses for a subrace. **GM only.**

    Full replace, not merge: the list in the request body becomes the
    complete set of bonuses for this subrace. Send an empty list to clear
    all bonuses.
    """

    return await race_service.set_ability_bonuses(race_id, subrace_id, data)
