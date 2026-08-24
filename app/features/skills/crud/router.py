"""Skill CRUD endpoints: paginated listing, get, create, update, delete."""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.constants import AbilityScore
from app.core.base.service import Page
from app.features.skills.crud.schemas import SkillCreate, SkillGetAllResponse, SkillResponse, SkillUpdate
from app.features.skills.dependencies import SkillCrudDep
from app.features.users.security import FounderDep, GmUserDep

router = APIRouter()


@router.get(
    "",
    response_model=Page[SkillGetAllResponse],
    summary="List skills",
)
async def get_skills(
    skill_service: SkillCrudDep,
    search: str | None = Query(
        None,
        description="Case-insensitive substring match against the skill's name and key.",
    ),
    ability: AbilityScore | None = Query(
        None,
        description="Exact match on the governing ability score (e.g. `WIS`).",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
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

    return await skill_service.get_all(page=page, size=size, search=search, filters={"ability": ability})


@router.get(
    "/{skill_id:int}",
    response_model=SkillResponse,
    summary="Get a skill by ID",
    responses={
        404: {"description": "Skill with id not found."},
    },
)
async def get_skill(skill_id: int, skill_service: SkillCrudDep):
    """
    Return a single skill by ID, with full detail.

    Open endpoint, no authentication required.
    """

    return await skill_service.get_by_id(skill_id)


@router.post(
    "",
    response_model=SkillResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a skill",
    responses={
        409: {"description": "A skill with this key already exists."},
    },
)
async def create_skill(
    data: Annotated[
        SkillCreate,
        Body(
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
    ],
    skill_service: SkillCrudDep,
    _: GmUserDep,
):
    """Create a new skill. **GM only.**"""

    return await skill_service.create(data)


@router.patch(
    "/{skill_id:int}",
    response_model=SkillResponse,
    summary="Update a skill",
    responses={
        404: {"description": "No skill exists with the given ID."},
        409: {"description": "Another skill already uses the requested key."},
    },
)
async def update_skill(
    skill_id: int,
    data: Annotated[
        SkillUpdate,
        Body(
            openapi_examples={
                "rename": {
                    "summary": "Rename the skill and edit its description",
                    "value": {
                        "name": "Perception",
                        "description": "Your Wisdom (Perception) check lets you spot, hear, or otherwise detect the presence of something.",
                    },
                },
            }
        ),
    ],
    skill_service: SkillCrudDep,
    _: GmUserDep,
):
    """
    Partially update a skill. **GM only.**

    Only fields included in the request body are changed; omitted fields
    are left as-is.
    """

    return await skill_service.update(skill_id, data)


@router.delete(
    "/{skill_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a skill",
    responses={
        404: {"description": "No skill exists with the given ID."},
        409: {"description": "Skill is still in use by a race, class, background, or character."},
    },
)
async def delete_skill(skill_id: int, skill_service: SkillCrudDep, _: FounderDep):
    """
    Delete a skill. **Founder only.**

    Blocked if the skill is still referenced by a race, class, background,
    or a character's skill proficiencies (the service raises
    ``RecordInUseError``, mapped to a 409 by the global exception handler).
    """

    await skill_service.delete(skill_id)
    return None
