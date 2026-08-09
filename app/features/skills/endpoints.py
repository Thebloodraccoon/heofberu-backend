"""Skill endpoints: listing and CRUD."""

from fastapi import APIRouter, Body, Query

from app.constants import AbilityScore
from app.core.base_service import Page
from app.core.dependencies import FounderDep, GmUserDep, SkillServiceDep
from app.features.skills.schemas import SkillCreate, SkillGetAllResponse, SkillResponse, SkillUpdate

router = APIRouter(prefix="/skills", tags=["Skills"])


@router.get(
    "/",
    response_model=Page[SkillGetAllResponse],
    summary="List skills",
)
def get_skills(
    skill_service: SkillServiceDep,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
    search: str | None = None,
    ability: AbilityScore | None = None,
):
    """
    Return a paginated list of skills with `id`, `key`, `name`, and
    `ability`.

    Open endpoint, no authentication required.

    `search` is a case-insensitive partial match against the skill name
    and key. `ability` is an exact match (e.g. `ability=WIS`) and can be
    combined with `search`.

    Response is `{items, total, page, size}` — `total` is the count of
    matching skills across every page, not just this one.

    Does not include the description — use `GET /skills/{skill_id}` for
    the full record.
    """

    return skill_service.get_all(page=page, size=size, search=search, filters={"ability": ability})


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

    return skill_service.create(skill_data)


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

    return skill_service.update(skill_id, update_data)


@router.delete(
    "/{skill_id}",
    status_code=204,
    summary="Delete a skill",
    responses={
        404: {"description": "No skill exists with the given ID."},
        409: {"description": "Skill is still in use by a race, class, background, or character."},
    },
)
def delete_skill(skill_id: int, skill_service: SkillServiceDep, _: FounderDep):
    """
    Delete a skill. **Found-father only.**

    Blocked if the skill is still referenced by a race, class, background,
    or a character's skill proficiencies (the service raises
    ``RecordInUseError``, mapped to a 409 by the global exception handler).
    """

    skill_service.delete(skill_id)
    return None
