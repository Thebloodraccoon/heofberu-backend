"""Race skill endpoints: full replacement of a race's granted skills."""

from typing import Annotated

from fastapi import APIRouter, Body

from app.features.races.dependencies import RaceSkillsDep
from app.features.races.schemas import RaceResponse, SkillsUpdate
from app.features.users.security import GmUserDep

router = APIRouter()


@router.put(
    "/{race_id:int}/skills",
    response_model=RaceResponse,
    summary="Replace a race's granted skills",
    responses={
        400: {"description": "One or more skill IDs don't correspond to an existing skill."},
        404: {"description": "No race exists with the given ID."},
    },
)
async def set_skills(
    race_id: int,
    data: Annotated[
        SkillsUpdate,
        Body(
            openapi_examples={
                "replace": {
                    "summary": "Replace with two skills",
                    "value": {"skill_ids": [3, 7]},
                },
                "clear": {
                    "summary": "Clear all granted skills",
                    "value": {"skill_ids": []},
                },
            },
        ),
    ],
    race_service: RaceSkillsDep,
    _: GmUserDep,
):
    """Replace all granted skills for a race. **GM only.**"""

    return await race_service.set_skills(race_id, data)
