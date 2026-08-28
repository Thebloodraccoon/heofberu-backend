"""
Background granted-skill endpoints.
``background_id`` is a path parameter supplied via the router prefix.
"""

from typing import Annotated

from fastapi import APIRouter, Body

from app.features.backgrounds.crud.schemas import BackgroundResponse
from app.features.backgrounds.dependencies import BackgroundSkillsDep
from app.features.backgrounds.skills.schemas import SkillsUpdate
from app.features.users.security import GmUserDep

router = APIRouter()


@router.put(
    "/skills",
    response_model=BackgroundResponse,
    summary="Replace a background's granted skills",
    responses={
        400: {"description": "One or more skill IDs don't correspond to an existing skill."},
        404: {"description": "No background exists with the given ID."},
    },
)
async def set_background_skills(
    background_id: int,
    data: Annotated[
        SkillsUpdate,
        Body(
            openapi_examples={
                "replace": {
                    "summary": "Replace with two skills",
                    "value": {"skill_ids": [4, 9]},
                },
                "clear": {
                    "summary": "Clear all granted skills",
                    "value": {"skill_ids": []},
                },
            },
        ),
    ],
    background_service: BackgroundSkillsDep,
    _: GmUserDep,
):
    """
    Replace all granted skills for a background. **GM only.**

    Full replace, not merge: the `skill_ids` in the request body become
    the complete set of skills this background grants — any skill not
    included is removed. Send an empty list to clear all granted skills.
    """

    return await background_service.set_skills(background_id, data)
