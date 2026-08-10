"""Background endpoints: listing, CRUD, and granted-skill management."""

from fastapi import APIRouter, Body, Query

from app.core.base_service import Page
from app.core.dependencies import BackgroundServiceDep, FounderDep, GmUserDep
from app.features.backgrounds.schemas import (
    BackgroundCreate,
    BackgroundGetAllResponse,
    BackgroundResponse,
    BackgroundUpdate,
    SkillsUpdate,
)
from app.features.features.schemas import FeatureUpdate, NestedFeatureCreate, NestedFeatureResponse

router = APIRouter(prefix="/backgrounds", tags=["Backgrounds"])


@router.get(
    "",
    response_model=Page[BackgroundGetAllResponse],
    summary="List backgrounds",
)
async def get_backgrounds(
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

    Response is `{items, total, page, size}` — `total` is the count of
    matching backgrounds across every page, not just this one.

    Does not include suggestion text, description, or features — use
    `GET /backgrounds/{background_id}` for the full record.
    """

    return await background_service.get_all(page=page, size=size, search=search)


@router.get(
    "/{background_id}",
    response_model=BackgroundResponse,
    summary="Get a background by ID",
    responses={
        404: {"description": "Background with id not found."},
    },
)
async def get_background(background_id: int, background_service: BackgroundServiceDep):
    """
    Return a single background by ID, with full detail — including
    granted skills.

    Open endpoint, no authentication required.
    """

    return await background_service.get_by_id(background_id)


@router.post(
    "",
    response_model=BackgroundResponse,
    status_code=201,
    summary="Create a background",
    responses={
        409: {"description": "A background with this name already exists."},
        400: {"description": "One or more `granted_skills` IDs don't correspond to an existing skill."},
    },
)
async def create_background(
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

    return await background_service.create_background(background_data, created_by_id=current_user.id)


@router.patch(
    "/{background_id}",
    response_model=BackgroundResponse,
    summary="Update a background's base fields",
    responses={
        404: {"description": "No background exists with the given ID."},
        409: {"description": "Another background already uses the requested name."},
    },
)
async def update_background(
    background_id: int, update_data: BackgroundUpdate, background_service: BackgroundServiceDep, _: GmUserDep
):
    """
    Partially update a background's base fields. **GM only.**

    Only fields included in the request body are changed; omitted fields
    are left as-is. Does not touch granted skills — use
    `PUT /backgrounds/{background_id}/skills` for that.
    """
    return await background_service.update(background_id, update_data)


@router.delete(
    "/{background_id}",
    status_code=204,
    summary="Delete a background",
    responses={
        404: {"description": "No background exists with the given ID."},
    },
)
async def delete_background(background_id: int, background_service: BackgroundServiceDep, _: FounderDep):
    """
    Delete a background. **Found-father only.**

    Also removes its links to granted skills and its features (cascade).
    Characters currently using this background have their `background_id`
    set to NULL rather than being blocked or deleted — deletion is only
    blocked (409) once one of its features has been granted to a
    character.
    """

    await background_service.delete(background_id)
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
async def set_background_skills(
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

    return await background_service.set_skills(background_id, data)


@router.get(
    "/{background_id}/features",
    response_model=list[NestedFeatureResponse],
    summary="List a background's features",
    responses={404: {"description": "No background exists with the given ID."}},
)
async def list_background_features(background_id: int, background_service: BackgroundServiceDep):
    """Return every feature owned by the background (``source_type: BACKGROUND``). Open endpoint."""

    return await background_service.list_features(background_id)


@router.post(
    "/{background_id}/features",
    response_model=NestedFeatureResponse,
    status_code=201,
    summary="Add a feature to a background",
    responses={
        404: {"description": "No background exists with the given ID."},
    },
)
async def add_background_feature(
    background_id: int,
    background_service: BackgroundServiceDep,
    _: GmUserDep,
    data: NestedFeatureCreate = Body(
        openapi_examples={
            "shelter": {
                "summary": "Add one feature",
                "value": {
                    "name": "Shelter of the Faithful",
                    "description": "You and your companions can expect free healing and care at a temple.",
                },
            },
        },
    ),
):
    """
    Add one feature to a background. **GM only.**

    The feature is created with ``source_type: BACKGROUND`` and becomes an
    auto-grant for every character bearing this background in the same
    transaction. Returns the created feature.

    ``level`` is not meaningful for background features and must stay
    ``null``.
    """

    return await background_service.add_feature(background_id, data, created_by_id=_.id)


@router.patch(
    "/{background_id}/features/{feature_id}",
    response_model=NestedFeatureResponse,
    summary="Update one feature of a background",
    responses={
        400: {"description": "The feature belongs to a different background, or the update is invalid."},
        404: {"description": "No background exists with the given ID, or no feature exists with the given ID."},
    },
)
async def update_background_feature(
    background_id: int,
    feature_id: int,
    background_service: BackgroundServiceDep,
    _: GmUserDep,
    data: FeatureUpdate = Body(
        openapi_examples={
            "rename": {
                "summary": "Edit one feature",
                "value": {
                    "name": "Shelter of the Faithful (Expanded)",
                    "description": "You and your companions can expect free healing and care at any shrine.",
                },
            },
        },
    ),
):
    """
    Update one feature of a background in place. **GM only.**

    The feature keeps its id, so character grants and any player notes on
    them survive. Only `name`, `level`, `description` and `is_homebrew`
    are editable; omitted fields are left as-is. Returns the updated
    feature.
    """

    return await background_service.update_feature(background_id, feature_id, data)


@router.delete(
    "/{background_id}/features/{feature_id}",
    status_code=204,
    summary="Remove a feature from a background",
    responses={
        400: {"description": "The feature belongs to a different background."},
        404: {"description": "No background exists with the given ID, or no feature exists with the given ID."},
    },
)
async def remove_background_feature(
    background_id: int,
    feature_id: int,
    background_service: BackgroundServiceDep,
    _: GmUserDep,
):
    """
    Remove one feature from a background. **GM only.**

    Deletes the feature, cascading away any `CharacterFeature` grants on
    it, and reconciles the affected characters in the same transaction.
    """

    await background_service.remove_feature(background_id, feature_id)
    return None
