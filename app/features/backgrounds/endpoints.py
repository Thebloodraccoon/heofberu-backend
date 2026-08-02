from fastapi import APIRouter, Body

from app.core.dependencies import BackgroundServiceDep, GmUserDep
from app.features.backgrounds.schemas import (
    BackgroundBriefResponse,
    BackgroundCreate,
    BackgroundResponse,
    BackgroundUpdate,
    SkillsUpdate,
)

router = APIRouter(prefix="/backgrounds", tags=["Backgrounds"])


@router.get(
    "/",
    response_model=list[BackgroundResponse],
    summary="List backgrounds (full detail)",
)
def get_backgrounds(
    background_service: BackgroundServiceDep,
    skip: int = 0,
    limit: int = 100,
    search: str | None = None,
):
    """
    Return a paginated list of backgrounds, each with full detail —
    including granted skills.

    Open endpoint, no authentication required.

    `search` is a case-insensitive partial match against the background
    name.

    For a lighter payload, use `GET /backgrounds/brief` instead.
    """
    return background_service.get_all(skip=skip, limit=limit, search=search)


@router.get(
    "/brief",
    response_model=list[BackgroundBriefResponse],
    summary="List backgrounds (minimal fields)",
)
def get_backgrounds_brief(
    background_service: BackgroundServiceDep,
    skip: int = 0,
    limit: int = 100,
    search: str | None = None,
):
    """
    Return a paginated list of backgrounds with only `id`, `name`,
    `is_homebrew`, and `granted_skills`.

    Open endpoint, no authentication required.

    `search` is a case-insensitive partial match against the background
    name.

    Does not include feature text, personality suggestions, or
    description — use `GET /backgrounds/{background_id}` for the full
    record. Intended for dropdowns, tables, and similar listing UI where
    the full payload is unnecessary.
    """
    return background_service.list_brief(skip=skip, limit=limit, search=search)


@router.get(
    "/{background_id}",
    response_model=BackgroundResponse,
    summary="Get a background by ID",
    responses={
        404: {"description": "Background with id not found."},
    },
)
def get_background(background_id: int, background_service: BackgroundServiceDep):
    """
    Return a single background by ID, with full detail — including
    granted skills.

    Open endpoint, no authentication required.
    """
    return background_service.get_by_id(background_id)


@router.post(
    "/",
    response_model=BackgroundResponse,
    status_code=201,
    summary="Create a background",
    responses={
        409: {"description": "A background with this name already exists."},
        400: {"description": "One or more `granted_skills` IDs don't correspond to an existing skill."},
    },
)
def create_background(
    background_service: BackgroundServiceDep,
    current_user: GmUserDep,
    background_data: BackgroundCreate = Body(
        openapi_examples={
            "minimal": {
                "summary": "Minimal — base fields only",
                "value": {"name": "Acolyte", "is_homebrew": "false"},
            },
            "with_skills": {
                "summary": "With feature and granted skills",
                "value": {
                    "name": "Acolyte",
                    "feature_name": "Shelter of the Faithful",
                    "feature_description": "You can perform religious ceremonies of your faith, and you and your companions can expect free healing and care at a temple, shrine, or other established presence of your faith.",
                    "personality_traits_suggestions": "I idolize a particular hero of my faith.\nI can find common ground between the fiercest enemies.",
                    "ideals_suggestions": "Tradition. The ancient traditions of worship and sacrifice must be preserved.",
                    "bonds_suggestions": "I would die to recover an ancient relic of my faith.",
                    "flaws_suggestions": "I judge others harshly, and myself even more severely.",
                    "description": "You have spent your life in the service of a temple.",
                    "is_homebrew": "false",
                    "granted_skills": [4, 9],
                },
            },
        },
    ),
):
    """
    Create a new background. **GM only.**

    `granted_skills` is optional. If provided, it's saved together with
    the background in a single transaction — the background is fully set
    up in one call instead of a `POST` followed by a `PUT`.
    """
    return background_service.create_background(background_data, created_by_id=current_user.id)


@router.patch(
    "/{background_id}",
    response_model=BackgroundResponse,
    summary="Update a background's base fields",
    responses={
        404: {"description": "No background exists with the given ID."},
        409: {"description": "Another background already uses the requested name."},
    },
)
def update_background(
    background_id: int, update_data: BackgroundUpdate, background_service: BackgroundServiceDep, _: GmUserDep
):
    """
    Partially update a background's base fields. **GM only.**

    Only fields included in the request body are changed; omitted fields
    are left as-is. Does not touch granted skills — use
    `PUT /backgrounds/{background_id}/skills` for that.
    """
    return background_service.update_background(background_id, update_data)


@router.delete(
    "/{background_id}",
    status_code=204,
    summary="Delete a background",
    responses={
        404: {"description": "No background exists with the given ID."},
    },
)
def delete_background(background_id: int, background_service: BackgroundServiceDep, _: GmUserDep):
    """
    Delete a background. **GM only.**

    Also removes its links to granted skills (cascade). Characters
    currently using this background have their `background_id` set to
    NULL rather than being blocked or deleted.
    """
    background_service.delete(background_id)
    return None


@router.put(
    "/{background_id}/skills",
    response_model=BackgroundResponse,
    summary="Replace a background's granted skills",
    responses={
        400: {"description": "One or more skill IDs don't correspond to an existing skill."},
        404: {"description": "No background exists with the given ID."},
    },
)
def set_background_skills(
    background_id: int,
    background_service: BackgroundServiceDep,
    _: GmUserDep,
    data: SkillsUpdate = Body(
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
):
    """
    Replace all granted skills for a background. **GM only.**

    Full replace, not merge: the `skill_ids` in the request body become
    the complete set of skills this background grants — any skill not
    included is removed. Send an empty list to clear all granted skills.
    """
    return background_service.set_skills(background_id, data)
