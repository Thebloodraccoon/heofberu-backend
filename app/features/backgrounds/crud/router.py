"""Background endpoints: listing, get-by-id, create, update, delete."""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.core.base.service import Page
from app.features.backgrounds.crud.schemas import (
    BackgroundCreate,
    BackgroundFullResponse,
    BackgroundGetAllResponse,
    BackgroundResponse,
    BackgroundUpdate,
)
from app.features.backgrounds.dependencies import BackgroundCrudDep
from app.features.users.security import FounderDep, GmUserDep

router = APIRouter()


@router.get(
    "",
    response_model=Page[BackgroundGetAllResponse],
    summary="List backgrounds",
)
async def get_backgrounds(
    background_service: BackgroundCrudDep,
    search: str | None = Query(
        None,
        description="Case-insensitive substring match against the background's name.",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
):
    """
    Return a paginated list of backgrounds with only `id`, `name`, and
    `granted_skills`.

    Open endpoint, no authentication required.

    `search` is a case-insensitive partial match against the background
    name.

    Response is `{items, total, page, size}` — `total` is the count of
    matching backgrounds across every page, not just this one.

    Does not include suggestion text, description, or features — use
    `GET /backgrounds/{background_id}` for the full record.
    """

    return await background_service.get_all(page=page, size=size, search=search)


@router.get(
    "/{background_id:int}",
    response_model=BackgroundFullResponse,
    summary="Get a background by ID",
    responses={
        404: {"description": "Background with id not found."},
    },
)
async def get_background(background_id: int, background_service: BackgroundCrudDep):
    """
    Return a single background by ID, with everything about it: base
    fields, granted skills, starting items, and its own BACKGROUND-source
    `features`.

    Cached as a single unit, so once warm this is one cache hit instead
    of a separate call to `.../features`.

    Open endpoint, no authentication required.
    """

    return await background_service.get_by_id(background_id)


@router.post(
    "",
    response_model=BackgroundResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a background",
    responses={
        409: {"description": "A background with this name already exists."},
        400: {"description": "One or more `granted_skills` IDs don't correspond to an existing skill."},
    },
)
async def create_background(
    data: Annotated[
        BackgroundCreate,
        Body(
            openapi_examples={
                "minimal": {
                    "summary": "Minimal — base fields only",
                    "value": {"name": "Acolyte"},
                },
                "with_skills": {
                    "summary": "With granted skills",
                    "value": {
                        "name": "Acolyte",
                        "personality_traits_suggestions": "I idolize a particular hero of my faith.\nI can find common ground between the fiercest enemies.",
                        "ideals_suggestions": "Tradition. The ancient traditions of worship and sacrifice must be preserved.",
                        "bonds_suggestions": "I would die to recover an ancient relic of my faith.",
                        "flaws_suggestions": "I judge others harshly, and myself even more severely.",
                        "description": "You have spent your life in the service of a temple.",
                        "granted_skills": [4, 9],
                    },
                },
            },
        ),
    ],
    background_service: BackgroundCrudDep,
    current_user: GmUserDep,
):
    """
    Create a new background. **GM only.**

    `granted_skills` is optional. If provided, it's saved together with
    the background in a single transaction.

    This endpoint is intentionally minimal: it does NOT accept `features`
    or `starting_items`. Attach those afterwards through their own
    endpoints:
    - `POST /backgrounds/{background_id}/features`
    - `PUT /backgrounds/{background_id}/items`
    """

    return await background_service.create_background(data, created_by_id=current_user.id)


@router.patch(
    "/{background_id:int}",
    response_model=BackgroundResponse,
    summary="Update a background's base fields",
    responses={
        404: {"description": "No background exists with the given ID."},
        409: {"description": "Another background already uses the requested name."},
    },
)
async def update_background(
    background_id: int,
    data: Annotated[
        BackgroundUpdate,
        Body(
            openapi_examples={
                "rename": {
                    "summary": "Rename the background and edit its description",
                    "value": {
                        "name": "Acolyte of the Dawn",
                        "description": "You have spent your life in the service of a temple of the Dawnfather.",
                    },
                },
            }
        ),
    ],
    background_service: BackgroundCrudDep,
    _: GmUserDep,
):
    """
    Partially update a background's base fields. **GM only.**

    Only fields included in the request body are changed; omitted fields
    are left as-is. Does not touch granted skills — use
    `PUT /backgrounds/{background_id}/skills` for that.
    """

    return await background_service.update(background_id, data)


@router.delete(
    "/{background_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a background",
    responses={
        404: {"description": "No background exists with the given ID."},
    },
)
async def delete_background(background_id: int, background_service: BackgroundCrudDep, _: FounderDep):
    """
    Delete a background. **Founder only.**

    Also removes its links to granted skills and its features (cascade).
    Characters currently using this background have their `background_id`
    set to NULL rather than being blocked or deleted — deletion is only
    blocked (409) once one of its features has been granted to a
    character.
    """

    await background_service.delete(background_id)
    return None
