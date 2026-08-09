"""Feat endpoints: listing, CRUD, and ASI-choice management."""

from fastapi import APIRouter, Body, Query

from app.core.base_service import Page
from app.core.dependencies import FeatServiceDep, FounderDep, GmUserDep
from app.features.feats.schemas import (
    AbilityScoreIncreasesUpdate,
    FeatCreate,
    FeatGetAllResponse,
    FeatResponse,
    FeatUpdate,
)
from app.features.features.schemas import FeaturesReplace

router = APIRouter(prefix="/feats", tags=["Feats"])


@router.get(
    "",
    response_model=Page[FeatGetAllResponse],
    summary="List feats",
)
async def get_feats(
    feat_service: FeatServiceDep,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
    search: str | None = None,
):
    """
    Return a paginated list of feats with only `id`, `name`, and
    `is_homebrew`.

    Open endpoint, no authentication required.

    `search` is a case-insensitive partial match against the feat name.

    Response is `{items, total, page, size}` — `total` is the count of
    matching feats across every page, not just this one.

    Does not include prerequisites or ability score increase choices —
    use `GET /feats/{feat_id}` for the full record.
    """

    return await feat_service.get_all(page=page, size=size, search=search)


@router.get(
    "/{feat_id}",
    response_model=FeatResponse,
    summary="Get a feat by ID",
    responses={
        404: {"description": "Feat with id not found."},
    },
)
async def get_feat(feat_id: int, feat_service: FeatServiceDep):
    """
    Return a single feat by ID, with full detail — including
    prerequisites, ability score increase choices, and features.

    Open endpoint, no authentication required.
    """

    return await feat_service.get_by_id(feat_id)


@router.post(
    "",
    response_model=FeatResponse,
    status_code=201,
    summary="Create a feat",
    responses={
        409: {"description": "A feat with this name already exists."},
    },
)
async def create_feat(
    feat_service: FeatServiceDep,
    current_user: GmUserDep,
    feat_data: FeatCreate = Body(
        openapi_examples={
            "no_prerequisite": {
                "summary": "No prerequisite, no ASI (e.g. Alert)",
                "value": {
                    "name": "Alert",
                    "description": "You gain a +5 bonus to initiative and can't be surprised while conscious.",
                    "is_homebrew": "false",
                },
            },
            "with_prerequisite": {
                "summary": "Ability score prerequisite (e.g. Heavy Armor Master)",
                "value": {
                    "name": "Heavy Armor Master",
                    "description": "While wearing heavy armor, bludgeoning, piercing, and slashing damage from nonmagical attacks is reduced by 3.",
                    "prerequisite_ability": "STR",
                    "prerequisite_minimum_score": 13,
                    "is_homebrew": "false",
                },
            },
            "with_asi_choice": {
                "summary": "Grants a choice of ASI (e.g. Resilient)",
                "value": {
                    "name": "Resilient",
                    "description": "Choose one ability score. You gain proficiency in saving throws using the chosen ability.",
                    "is_homebrew": "false",
                    "ability_score_increases": [
                        {"ability": "STR", "amount": 1},
                        {"ability": "DEX", "amount": 1},
                        {"ability": "CON", "amount": 1},
                        {"ability": "INT", "amount": 1},
                        {"ability": "WIS", "amount": 1},
                        {"ability": "CHA", "amount": 1},
                    ],
                },
            },
            "with_features": {
                "summary": "With nested features (e.g. Alert)",
                "value": {
                    "name": "Alert",
                    "description": "You gain a +5 bonus to initiative and can't be surprised while conscious.",
                    "features": [
                        {
                            "name": "Alert Initiative",
                            "description": "You gain a +5 bonus to initiative.",
                        },
                        {
                            "name": "Cannot Be Surprised",
                            "description": "You can't be surprised while conscious.",
                        },
                    ],
                },
            },
        },
    ),
):
    """
    Create a new feat. **GM only.**

    `ability_score_increases` and `features` are optional. If provided,
    they're saved together with the feat in a single transaction — the
    feat is fully set up in one call instead of a `POST` followed by a
    `PUT`. Nested `features` become FEAT-source features that any
    character granted this feat gains automatically.
    """

    return await feat_service.create_feat(feat_data, created_by_id=current_user.id)


@router.patch(
    "/{feat_id}",
    response_model=FeatResponse,
    summary="Update a feat's base fields",
    responses={
        404: {"description": "No feat exists with the given ID."},
        409: {"description": "Another feat already uses the requested name."},
    },
)
async def update_feat(feat_id: int, update_data: FeatUpdate, feat_service: FeatServiceDep, _: GmUserDep):
    """
    Partially update a feat's base fields. **GM only.**

    Only fields included in the request body are changed; omitted fields
    are left as-is. Does not touch ability score increase choices — use
    `PUT /feats/{feat_id}/ability-score-increases` for those.
    """

    return await feat_service.update(feat_id, update_data)


@router.delete(
    "/{feat_id}",
    status_code=204,
    summary="Delete a feat",
    responses={
        404: {"description": "No feat exists with the given ID."},
        409: {"description": "Feat is still in use by one or more characters or features."},
    },
)
async def delete_feat(feat_id: int, feat_service: FeatServiceDep, _: FounderDep):
    """
    Delete a feat. **Found-father only.**

    Also removes its ability score increase choices and its features
    (cascade). Blocked if the feat is still granted to one or more
    characters, or one of its features is still granted to a character.
    """

    await feat_service.delete(feat_id)
    return None


@router.put(
    "/{feat_id}/ability-score-increases",
    response_model=FeatResponse,
    summary="Replace a feat's ability score increase choices",
    responses={
        404: {"description": "No feat exists with the given ID."},
    },
)
async def set_feat_ability_score_increases(
    feat_id: int,
    feat_service: FeatServiceDep,
    _: GmUserDep,
    data: AbilityScoreIncreasesUpdate = Body(
        openapi_examples={
            "replace": {
                "summary": "Replace with two choices",
                "value": {
                    "ability_score_increases": [{"ability": "STR", "amount": 1}, {"ability": "CON", "amount": 1}]
                },
            },
            "clear": {
                "summary": "Clear all ASI choices",
                "value": {"ability_score_increases": []},
            },
        },
    ),
):
    """
    Replace all ability score increase choices for a feat. **GM only.**

    Full replace, not merge: the list in the request body becomes the
    complete set of ASI choices for this feat — any choice not included
    is removed. Send an empty list to clear all choices (the feat then
    grants no ability score increase of its own).
    """

    return await feat_service.set_ability_score_increases(feat_id, data)


@router.put(
    "/{feat_id}/features",
    response_model=FeatResponse,
    summary="Replace a feat's features",
    responses={
        400: {"description": "An item's feature id does not belong to this feat."},
        422: {"description": "Duplicate feature ids in one request."},
        404: {"description": "No feat exists with the given ID."},
    },
)
async def replace_feat_features(
    feat_id: int,
    feat_service: FeatServiceDep,
    _: GmUserDep,
    data: FeaturesReplace = Body(
        openapi_examples={
            "replace": {
                "summary": "Replace the feat feature list (matched by id)",
                "value": {
                    "features": [
                        {
                            "id": 8,
                            "name": "Alert Initiative",
                            "description": "You gain a +5 bonus to initiative.",
                        },
                        {
                            "name": "Never Startled",
                            "description": "You always act in the surprise round.",
                        },
                    ]
                },
            },
            "clear": {
                "summary": "Remove all feat features",
                "value": {"features": []},
            },
        },
    ),
):
    """
    Replace a feat's feature list. **GM only.**

    Full replace, not merge, matched by feature `id`:

    - items carrying an `id` update that existing feature in place — the
      feature keeps its id, so any character grants (and notes on them)
      survive the update;
    - items without an `id` create new features;
    - current features whose id is not in the request body are deleted,
      which cascades away their character grants.

    Send `{"features": []}` to delete every feature of the feat. An `id`
    that doesn't belong to this feat is rejected with 400; duplicate ids
    within one request are rejected with 422.
    """

    return await feat_service.replace_feat_features(feat_id, data, created_by_id=_.id)
