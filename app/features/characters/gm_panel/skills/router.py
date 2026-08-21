"""
GM skill-expertise endpoint: PATCH under ``/gm-panel/skills/{skill_id}``.

The sub-router declares no prefix of its own; the panel's aggregating
router applies ``/{character_id}/gm-panel``.
"""

from fastapi import APIRouter

from app.core.security.dependencies import GmUserDep
from app.features.characters.gm_panel.dependencies import GmPanelSkillsDep
from app.features.characters.gm_panel.skills.schemas import SkillExpertiseUpdate
from app.features.characters.schemas import SkillProficiencyResponse

router = APIRouter()


@router.patch(
    "/skills/{skill_id}",
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
    skill_id: int,
    data: SkillExpertiseUpdate,
    skills_service: GmPanelSkillsDep,
    current_user: GmUserDep,
):
    """
    Set or clear the `is_expertise` flag on one of the character's skill
    proficiencies. GM-only endpoint.

    Expertise is never derived automatically — the flag is stored on the
    proficiency row and echoed back on every character read
    (`skill_proficiencies[].is_expertise`), where clients double the
    level-based proficiency bonus for it. The character must already be
    proficient in the skill: rows are written once at creation (class
    choices plus background/race grants) and are never added here.
    """

    return await skills_service.set_expertise(character_id, skill_id, data, current_user)
