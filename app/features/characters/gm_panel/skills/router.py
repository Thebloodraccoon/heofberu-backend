"""GM skill-expertise endpoint: PATCH /gm-panel/skills (query-style IDs)."""

from typing import Annotated

from fastapi import APIRouter, Body, Query

from app.features.characters.gm_panel.dependencies import GmPanelSkillsDep
from app.features.characters.gm_panel.skills.schemas import SkillExpertiseUpdate
from app.features.characters.schemas import SkillProficiencyResponse
from app.features.users.security import GmUserDep

router = APIRouter()


@router.patch(
    "/skills",
    response_model=SkillProficiencyResponse,
    summary="Toggle expertise on one of a character's skill proficiencies",
    responses={
        403: {"description": "You are not a GM."},
        404: {
            "description": (
                "No character exists with the given ID, or the character is not "
                "proficient in this skill (expertise requires proficiency)."
            )
        },
    },
)
async def set_character_skill_expertise(
    character_id: int,
    skill_id: Annotated[int, Query(gt=0)],
    data: Annotated[
        SkillExpertiseUpdate,
        Body(
            openapi_examples={
                "grant": {
                    "summary": "Grant expertise in Stealth",
                    "value": {"is_expertise": True},
                },
                "revoke": {
                    "summary": "Revoke expertise again",
                    "value": {"is_expertise": False},
                },
            }
        ),
    ],
    skills_service: GmPanelSkillsDep,
    current_user: GmUserDep,
):
    """Set or clear the is_expertise flag on a skill proficiency (expertise requires proficiency). **GM only.**"""

    return await skills_service.set_expertise(character_id, skill_id, data, current_user)
