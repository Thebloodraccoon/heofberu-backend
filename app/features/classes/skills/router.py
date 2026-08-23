"""Class available-skills endpoint."""

from fastapi import APIRouter, Body

from app.features.classes.dependencies import ClassSkillsDep
from app.features.classes.schemas import AvailableSkillsUpdate, ClassResponse
from app.features.users.security import GmUserDep

router = APIRouter()


@router.put(
    "/{class_id}/available-skills",
    response_model=ClassResponse,
    summary="Replace a class's available skills",
    responses={
        400: {"description": "One or more skill IDs don't correspond to an existing skill."},
        404: {"description": "No class exists with the given ID."},
    },
)
async def set_class_available_skills(
    class_id: int,
    class_service: ClassSkillsDep,
    _: GmUserDep,
    data: AvailableSkillsUpdate = Body(
        openapi_examples={
            "replace": {
                "summary": "Replace with two skills",
                "value": {"skill_ids": [3, 7]},
            },
            "clear": {
                "summary": "Clear all available skills",
                "value": {"skill_ids": []},
            },
        },
    ),
):
    """
    Replace all skills a class may choose proficiencies from. **GM only.**

    Full replace, not merge: the `skill_ids` in the request body become
    the complete set of skills this class offers — any skill not included
    is removed. Send an empty list to clear all available skills.
    """

    return await class_service.set_available_skills(class_id, data)
