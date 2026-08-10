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
from app.features.features.schemas import FeatureUpdate, NestedFeatureCreate, NestedFeatureResponse

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
    prerequisites and ability score increase choices.

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


@router.get(
    "/{feat_id}/features",
    response_model=list[NestedFeatureResponse],
    summary="List a feat's features",
    responses={404: {"description": "No feat exists with the given ID."}},
)
async def list_feat_features(feat_id: int, feat_service: FeatServiceDep):
    """Return every feature owned by the feat (``source_type: FEAT``). Open endpoint."""

    return await feat_service.list_features(feat_id)


@router.post(
    "/{feat_id}/features",
    response_model=NestedFeatureResponse,
    status_code=201,
    summary="Add a feature to a feat",
    responses={
        404: {"description": "No feat exists with the given ID."},
    },
)
async def add_feat_feature(
    feat_id: int,
    feat_service: FeatServiceDep,
    _: GmUserDep,
    data: NestedFeatureCreate = Body(
        openapi_examples={
            "alert_initiative": {
                "summary": "Add one feature",
                "value": {
                    "name": "Alert Initiative",
                    "description": "You gain a +5 bonus to initiative.",
                },
            },
        },
    ),
):
    """
    Add one feature to a feat. **GM only.**

    The feature is created with ``source_type: FEAT`` and becomes an
    auto-grant for every character holding this feat in the same
    transaction. Returns the created feature.

    ``level`` is not meaningful for feat features and must stay ``null``.
    """

    return await feat_service.add_feature(feat_id, data, created_by_id=_.id)


@router.patch(
    "/{feat_id}/features/{feature_id}",
    response_model=NestedFeatureResponse,
    summary="Update one feature of a feat",
    responses={
        400: {"description": "The feature belongs to a different feat, or the update is invalid."},
        404: {"description": "No feat exists with the given ID, or no feature exists with the given ID."},
    },
)
async def update_feat_feature(
    feat_id: int,
    feature_id: int,
    feat_service: FeatServiceDep,
    _: GmUserDep,
    data: FeatureUpdate = Body(
        openapi_examples={
            "rename": {
                "summary": "Edit one feature",
                "value": {
                    "name": "Alert Initiative (Improved)",
                    "description": "You gain a +10 bonus to initiative.",
                },
            },
        },
    ),
):
    """
    Update one feature of a feat in place. **GM only.**

    The feature keeps its id, so character grants and any player notes on
    them survive. Only `name`, `level`, `description` and `is_homebrew`
    are editable; omitted fields are left as-is. Returns the updated
    feature.
    """

    return await feat_service.update_feature(feat_id, feature_id, data)


@router.delete(
    "/{feat_id}/features/{feature_id}",
    status_code=204,
    summary="Remove a feature from a feat",
    responses={
        400: {"description": "The feature belongs to a different feat."},
        404: {"description": "No feat exists with the given ID, or no feature exists with the given ID."},
    },
)
async def remove_feat_feature(
    feat_id: int,
    feature_id: int,
    feat_service: FeatServiceDep,
    _: GmUserDep,
):
    """
    Remove one feature from a feat. **GM only.**

    Deletes the feature, cascading away any `CharacterFeature` grants on
    it, and reconciles the affected characters in the same transaction.
    """

    await feat_service.remove_feature(feat_id, feature_id)
    return None
