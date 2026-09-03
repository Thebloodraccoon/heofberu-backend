"""Background granted-skill endpoints."""

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

    Full replace (not merge): the given `skill_ids` become the complete
    set; send an empty list to clear them all.
    """

    return await background_service.set_skills(background_id, data)
