"""
Race feature endpoints: per-race RACE-source feature CRUD (query-style
IDs — the race is identified by the required ``race_id`` query
parameter).
"""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.features.races.dependencies import RaceFeaturesDep
from app.features.shared.features.schemas import FeatureUpdate, NestedFeatureCreate, NestedFeatureResponse
from app.features.users.security import GmUserDep

router = APIRouter()


@router.get(
    "/features",
    response_model=list[NestedFeatureResponse],
    summary="List a race's features",
    responses={404: {"description": "No race exists with the given ID."}},
)
async def list_features(race_id: Annotated[int, Query(gt=0)], race_service: RaceFeaturesDep):
    """Return every feature owned by the race (``source_type: RACE``). Open endpoint."""

    return await race_service.list_features(race_id)


@router.post(
    "/features",
    response_model=NestedFeatureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a feature to a race",
    responses={
        404: {"description": "No race exists with the given ID."},
    },
)
async def add_feature(
    race_id: Annotated[int, Query(gt=0)],
    data: Annotated[
        NestedFeatureCreate,
        Body(
            openapi_examples={
                "darkvision": {
                    "summary": "Add one feature",
                    "value": {
                        "name": "Darkvision",
                        "description": "See in dim light within 60 ft.",
                    },
                },
            },
        ),
    ],
    race_service: RaceFeaturesDep,
    current_user: GmUserDep,
):
    """
    Add one feature to a race. **GM only.**

    The feature is created with ``source_type: RACE`` and becomes an
    auto-grant for every character of this race (level-gated where
    applicable) in the same transaction. Returns the created feature.

    ``level`` is not meaningful for race features and must stay ``null``.
    """

    return await race_service.add_feature(race_id, data)


@router.patch(
    "/features",
    response_model=NestedFeatureResponse,
    summary="Update one feature of a race",
    responses={
        400: {"description": "The feature belongs to a different race, or the update is invalid."},
        404: {"description": "No race exists with the given ID, or no feature exists with the given ID."},
    },
)
async def update_feature(
    race_id: Annotated[int, Query(gt=0)],
    feature_id: Annotated[int, Query(gt=0)],
    data: Annotated[
        FeatureUpdate,
        Body(
            openapi_examples={
                "rename": {
                    "summary": "Edit one feature",
                    "value": {
                        "name": "Darkvision (Improved)",
                        "description": "See in dim light within 120 ft.",
                    },
                },
            },
        ),
    ],
    race_service: RaceFeaturesDep,
    _: GmUserDep,
):
    """
    Update one feature of a race in place. **GM only.**

    The feature keeps its id, so character grants and any player notes on
    them survive. Only `name`, `level`, `description` are
    editable; omitted fields are left as-is. Returns the updated
    feature.
    """

    return await race_service.update_feature(race_id, feature_id, data)


@router.delete(
    "/features",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a feature from a race",
    responses={
        400: {"description": "The feature belongs to a different race."},
        404: {"description": "No race exists with the given ID, or no feature exists with the given ID."},
    },
)
async def remove_feature(
    race_id: Annotated[int, Query(gt=0)],
    feature_id: Annotated[int, Query(gt=0)],
    race_service: RaceFeaturesDep,
    _: GmUserDep,
):
    """
    Remove one feature from a race. **GM only.**

    Deletes the feature, cascading away any `CharacterFeature` grants on
    it, and reconciles the affected characters in the same transaction.
    """

    await race_service.remove_feature(race_id, feature_id)
    return None
