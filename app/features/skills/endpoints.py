from fastapi import APIRouter, Body

from app.core.dependencies import GmUserDep, SkillServiceDep
from app.features.skills.schemas import SkillBriefResponse, SkillCreate, SkillResponse, SkillUpdate

router = APIRouter(prefix="/skills", tags=["Skills"])


@router.get(
    "/",
    response_model=list[SkillResponse],
    summary="List skills (full detail)",
)
def get_skills(skill_service: SkillServiceDep):
    """
    Return every skill, with full detail, ordered by name.

    Open endpoint, no authentication required.

    For a lighter payload, use `GET /skills/brief` instead.
    """
    return skill_service.get_all()


@router.get(
    "/brief",
    response_model=list[SkillBriefResponse],
    summary="List skills (minimal fields)",
)
def get_skills_brief(skill_service: SkillServiceDep, skip: int = 0, limit: int = 100):
    """
    Return a paginated list of skills with only `id`, `key`, `name`, and
    `ability`.

    Open endpoint, no authentication required.

    Does not include the description — use `GET /skills/{skill_id}` for
    the full record. Intended for dropdowns, tables, and similar listing
    UI where the full payload is unnecessary.
    """
    return skill_service.list_brief(skip=skip, limit=limit)


@router.get(
    "/{skill_id}",
    response_model=SkillResponse,
    summary="Get a skill by ID",
    responses={
        404: {"description": "Skill with id not found."},
    },
)
def get_skill(skill_id: int, skill_service: SkillServiceDep):
    """
    Return a single skill by ID, with full detail.

    Open endpoint, no authentication required.
    """
    return skill_service.get_by_id(skill_id)


@router.post(
    "/",
    response_model=SkillResponse,
    status_code=201,
    summary="Create a skill",
    responses={
        409: {"description": "A skill with this key already exists."},
    },
)
def create_skill(
    skill_service: SkillServiceDep,
    _: GmUserDep,
    skill_data: SkillCreate = Body(
        openapi_examples={
            "minimal": {
                "summary": "Minimal — no description",
                "value": {
                    "key": "STEALTH",
                    "name": "Stealth",
                    "ability": "DEX",
                },
            },
            "full": {
                "summary": "Full — with description",
                "value": {
                    "key": "PERCEPTION",
                    "name": "Perception",
                    "ability": "WIS",
                    "description": "Your Wisdom (Perception) check lets you spot, hear, or otherwise detect the presence of something.",
                },
            },
        },
    ),
):
    """Create a new skill. **GM only.**"""
    return skill_service.create_skill(skill_data)


@router.patch(
    "/{skill_id}",
    response_model=SkillResponse,
    summary="Update a skill",
    responses={
        404: {"description": "No skill exists with the given ID."},
        409: {"description": "Another skill already uses the requested key."},
    },
)
def update_skill(skill_id: int, update_data: SkillUpdate, skill_service: SkillServiceDep, _: GmUserDep):
    """
    Partially update a skill. **GM only.**

    Only fields included in the request body are changed; omitted fields
    are left as-is.
    """
    return skill_service.update_skill(skill_id, update_data)


@router.delete(
    "/{skill_id}",
    status_code=204,
    summary="Delete a skill",
    responses={
        404: {"description": "No skill exists with the given ID."},
        409: {"description": "Skill is still in use by a race, class, background, or character."},
    },
)
def delete_skill(skill_id: int, skill_service: SkillServiceDep, _: GmUserDep):
    """
    Delete a skill. **GM only.**

    Blocked if the skill is still referenced by a race, class, background,
    or a character's skill proficiencies (raises `SkillInUseException`,
    mapped to a 409 by the global exception handler).
    """
    skill_service.delete_skill(skill_id)
    return None
