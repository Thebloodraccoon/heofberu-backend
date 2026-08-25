"""
Background feature endpoints: per-background BACKGROUND-source feature
CRUD (query-style IDs — the background is identified by the required
``background_id`` query parameter).
"""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.features.backgrounds.dependencies import BackgroundFeaturesDep
from app.features.backgrounds.features.schemas import FeatureUpdate, NestedFeatureCreate, NestedFeatureResponse
from app.features.users.security import GmUserDep

router = APIRouter()


@router.get(
    "/features",
    response_model=list[NestedFeatureResponse],
    summary="List a background's features",
    responses={404: {"description": "No background exists with the given ID."}},
)
async def list_background_features(
    background_id: Annotated[int, Query(gt=0)], background_service: BackgroundFeaturesDep
):
    """Return every feature owned by the background (``source_type: BACKGROUND``). Open endpoint."""

    return await background_service.list_features(background_id)


@router.post(
    "/features",
    response_model=NestedFeatureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a feature to a background",
    responses={
        404: {"description": "No background exists with the given ID."},
    },
)
async def add_background_feature(
    background_id: Annotated[int, Query(gt=0)],
    data: Annotated[
        NestedFeatureCreate,
        Body(
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
    ],
    background_service: BackgroundFeaturesDep,
    current_user: GmUserDep,
):
    """
    Add one feature to a background. **GM only.**

    The feature is created with ``source_type: BACKGROUND`` and becomes an
    auto-grant for every character bearing this background in the same
    transaction. Returns the created feature.

    ``level`` is not meaningful for background features and must stay
    ``null``.
    """

    return await background_service.add_feature(background_id, data)


@router.patch(
    "/features",
    response_model=NestedFeatureResponse,
    summary="Update one feature of a background",
    responses={
        400: {"description": "The feature belongs to a different background, or the update is invalid."},
        404: {"description": "No background exists with the given ID, or no feature exists with the given ID."},
    },
)
async def update_background_feature(
    background_id: Annotated[int, Query(gt=0)],
    feature_id: Annotated[int, Query(gt=0)],
    data: Annotated[
        FeatureUpdate,
        Body(
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
    ],
    background_service: BackgroundFeaturesDep,
    _: GmUserDep,
):
    """
    Update one feature of a background in place. **GM only.**

    The feature keeps its id, so character grants and any player notes on
    them survive. Only `name`, `level`, `description` are
    editable; omitted fields are left as-is. Returns the updated
    feature.
    """

    return await background_service.update_feature(background_id, feature_id, data)


@router.delete(
    "/features",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a feature from a background",
    responses={
        400: {"description": "The feature belongs to a different background."},
        404: {"description": "No background exists with the given ID, or no feature exists with the given ID."},
    },
)
async def remove_background_feature(
    background_id: Annotated[int, Query(gt=0)],
    feature_id: Annotated[int, Query(gt=0)],
    background_service: BackgroundFeaturesDep,
    _: GmUserDep,
):
    """
    Remove one feature from a background. **GM only.**

    Deletes the feature, cascading away any `CharacterFeature` grants on
    it, and reconciles the affected characters in the same transaction.
    """

    await background_service.remove_feature(background_id, feature_id)
    return None
