"""Subrace ability-bonus endpoints: full replacement of a subrace's bonuses."""

from typing import Annotated

from fastapi import APIRouter, Body

from app.core.types import EntityIdPath
from app.features.auth.dependencies import GmUserDep
from app.features.shared.catalog.schemas import AbilityBonusesUpdate
from app.features.subraces.crud.schemas import SubraceResponse
from app.features.subraces.dependencies import SubraceAbilityBonusesDep

router = APIRouter()


@router.put(
    "/{subrace_id:int}/ability-bonuses",
    response_model=SubraceResponse,
    summary="Replace a subrace's ability bonuses",
    responses={404: {"description": "No subrace exists with the given ID."}},
)
async def set_ability_bonuses(
    subrace_id: EntityIdPath,
    data: Annotated[
        AbilityBonusesUpdate,
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
    subrace_service: SubraceAbilityBonusesDep,
    _: GmUserDep,
):
    """Replace all ability score bonuses for a subrace. **GM only.**"""

    return await subrace_service.set_ability_bonuses(subrace_id, data)
