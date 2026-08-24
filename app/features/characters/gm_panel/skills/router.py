"""
GM skill-expertise endpoint: PATCH under ``/gm-panel/skills`` (query-style
IDs).

The sub-router declares no prefix of its own; the panel's aggregating
router applies ``/gm-panel``. The character and the proficiency are
identified by the required ``character_id`` / ``skill_id`` query
parameters.
"""

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
    character_id: Annotated[int, Query(gt=0)],
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
    """
    Set or clear the `is_expertise` flag on one of the character's skill
    proficiencies. Expertise is never derived automatically — the flag is
    stored on the proficiency row and echoed back on every character read
    (`skill_proficiencies[].is_expertise`), where clients double the
    level-based proficiency bonus for it. The character must already be
    proficient in the skill: rows are written once at creation (class
    choices plus background/race grants) and are never added here.
    **GM only.**
    """

    return await skills_service.set_expertise(character_id, skill_id, data, current_user)
