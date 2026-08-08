"""Background endpoints: listing, CRUD, and granted-skill management."""

from fastapi import APIRouter, Body, Query

from app.core.base_service import Page
from app.core.dependencies import BackgroundServiceDep, FounderDep, GmUserDep
from app.features.backgrounds.schemas import (
    BackgroundBriefResponse,
    BackgroundCreate,
    BackgroundResponse,
    BackgroundUpdate,
    SkillsUpdate,
)
from app.features.features.schemas import FeaturesReplace

router = APIRouter(prefix="/backgrounds", tags=["Backgrounds"])


@router.get(
    "/",
    response_model=Page[BackgroundResponse],
    summary="List backgrounds (full detail)",
)
def get_backgrounds(
    background_service: BackgroundServiceDep,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
    search: str | None = None,
):
    """
    Return a paginated list of backgrounds, each with full detail —
    including granted skills and features.

    Open endpoint, no authentication required.

    `search` is a case-insensitive partial match against the background
    name.

    Response is `{items, total, page, size}` — `total` is the count of
    matching backgrounds across every page, not just this one.

    For a lighter payload, use `GET /backgrounds/brief` instead.
    """
    return background_service.get_all(page=page, size=size, search=search)


@router.get(
    "/brief",
    response_model=Page[BackgroundBriefResponse],
    summary="List backgrounds (minimal fields)",
)
def get_backgrounds_brief(
    background_service: BackgroundServiceDep,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
    search: str | None = None,
):
    """
    Return a paginated list of backgrounds with only `id`, `name`,
    `is_homebrew`, and `granted_skills`.

    Open endpoint, no authentication required.

    `search` is a case-insensitive partial match against the background
    name.

    Response is `{items, total, page, size}`, same shape as `GET /backgrounds/`.

    Does not include suggestion text, description, or features — use
    `GET /backgrounds/{background_id}` for the full record. Intended for
    dropdowns, tables, and similar listing UI where the full payload is
    unnecessary.
    """
    return background_service.list_brief(page=page, size=size, search=search)


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
    granted skills and features.

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
            "with_skills_and_features": {
                "summary": "With granted skills and nested features",
                "value": {
                    "name": "Acolyte",
                    "personality_traits_suggestions": "I idolize a particular hero of my faith.\nI can find common ground between the fiercest enemies.",
                    "ideals_suggestions": "Tradition. The ancient traditions of worship and sacrifice must be preserved.",
                    "bonds_suggestions": "I would die to recover an ancient relic of my faith.",
                    "flaws_suggestions": "I judge others harshly, and myself even more severely.",
                    "description": "You have spent your life in the service of a temple.",
                    "is_homebrew": "false",
                    "granted_skills": [4, 9],
                    "features": [
                        {
                            "name": "Shelter of the Faithful",
                            "description": "You can perform religious ceremonies of your faith, and you and your companions can expect free healing and care at a temple, shrine, or other established presence of your faith.",
                        }
                    ],
                },
            },
        },
    ),
):
    """
    Create a new background. **GM only.**

    `granted_skills` and `features` are optional. If provided, they're
    saved together with the background in a single transaction — the
    background is fully set up in one call instead of a `POST` followed
    by a `PUT`. Nested `features` become BACKGROUND-source features that
    every character bearing this background gains automatically.
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
    return background_service.update(background_id, update_data)


@router.delete(
    "/{background_id}",
    status_code=204,
    summary="Delete a background",
    responses={
        404: {"description": "No background exists with the given ID."},
    },
)
def delete_background(background_id: int, background_service: BackgroundServiceDep, _: FounderDep):
    """
    Delete a background. **Found-father only.**

    Also removes its links to granted skills and its features (cascade).
    Characters currently using this background have their `background_id`
    set to NULL rather than being blocked or deleted — deletion is only
    blocked (409) once one of its features has been granted to a
    character.
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


@router.put(
    "/{background_id}/features",
    response_model=BackgroundResponse,
    summary="Replace a background's features",
    responses={
        400: {"description": "An item's feature id does not belong to this background."},
        422: {"description": "Duplicate feature ids in one request."},
        404: {"description": "No background exists with the given ID."},
    },
)
def replace_background_features(
    background_id: int,
    background_service: BackgroundServiceDep,
    _: GmUserDep,
    data: FeaturesReplace = Body(
        openapi_examples={
            "replace": {
                "summary": "Replace the background feature list (matched by id)",
                "value": {
                    "features": [
                        {
                            "id": 5,
                            "name": "Shelter of the Faithful",
                            "description": "You can perform religious ceremonies of your faith.",
                        },
                        {
                            "name": "Devotion",
                            "description": "You have a personal devotional practice.",
                        },
                    ]
                },
            },
            "clear": {
                "summary": "Remove all background features",
                "value": {"features": []},
            },
        },
    ),
):
    """
    Replace a background's feature list. **GM only.**

    Full replace, not merge, matched by feature `id`:

    - items carrying an `id` update that existing feature in place — the
      feature keeps its id, so any character grants (and notes on them)
      survive the update;
    - items without an `id` create new features;
    - current features whose id is not in the request body are deleted,
      which cascades away their character grants.

    Send `{"features": []}` to delete every feature of the background. An
    `id` that doesn't belong to this background is rejected with 400;
    duplicate ids within one request are rejected with 422.
    """
    return background_service.replace_background_features(background_id, data, created_by_id=_.id)
