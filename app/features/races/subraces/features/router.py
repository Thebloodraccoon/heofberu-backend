"""
Subrace feature endpoints: per-subrace SUBRACE-source feature CRUD
(query-style IDs).

The router declares no prefix of its own; ``app.features.races.router``
applies the ``/races`` prefix and ``app.features.races.subraces.router``
the static ``/subraces`` prefix — combined, ``"/features"`` resolves to
``/races/subraces/features?race_id=...&subrace_id=...``. Both the owning
race and the subrace are identified by required query parameters.
"""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.features.races.subraces.dependencies import SubraceFeaturesDep
from app.features.races.subraces.features.schemas import FeatureUpdate, NestedFeatureCreate, NestedFeatureResponse
from app.features.users.security import GmUserDep

router = APIRouter()


@router.get(
    "/features",
    response_model=list[NestedFeatureResponse],
    summary="List a subrace's features",
    responses={404: {"description": "No subrace exists with the given ID under this race."}},
)
async def list_features(
    race_id: Annotated[int, Query(gt=0)],
    subrace_id: Annotated[int, Query(gt=0)],
    race_service: SubraceFeaturesDep,
):
    """Return every feature owned by the subrace (``source_type: SUBRACE``). Open endpoint."""

    return await race_service.list_features(race_id, subrace_id)


@router.post(
    "/features",
    response_model=NestedFeatureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a feature to a subrace",
    responses={404: {"description": "No subrace exists with the given ID under this race."}},
)
async def add_feature(
    race_id: Annotated[int, Query(gt=0)],
    subrace_id: Annotated[int, Query(gt=0)],
    data: Annotated[
        NestedFeatureCreate,
        Body(
            openapi_examples={
                "darkvision": {
                    "summary": "Add one feature",
                    "value": {
                        "name": "Drow Magic",
                        "description": "Know the dancing lights cantrip.",
                    },
                },
            },
        ),
    ],
    race_service: SubraceFeaturesDep,
    current_user: GmUserDep,
):
    """
    Add one feature to a subrace. **GM only.**

    The feature is created with ``source_type: SUBRACE`` and becomes an
    auto-grant for every character of this subrace in the same
    transaction. Returns the created feature.

    ``level`` is not meaningful for subrace features and must stay ``null``.
    """

    return await race_service.add_feature(race_id, subrace_id, data, created_by_id=current_user.id)


@router.patch(
    "/features",
    response_model=NestedFeatureResponse,
    summary="Update one feature of a subrace",
    responses={
        400: {"description": "The feature belongs to a different subrace, or the update is invalid."},
        404: {
            "description": "No subrace exists with the given ID under this race, or no feature exists with the given ID."
        },
    },
)
async def update_feature(
    race_id: Annotated[int, Query(gt=0)],
    subrace_id: Annotated[int, Query(gt=0)],
    feature_id: Annotated[int, Query(gt=0)],
    data: Annotated[
        FeatureUpdate,
        Body(
            openapi_examples={
                "rename": {
                    "summary": "Edit one feature",
                    "value": {
                        "name": "Drow Magic (Improved)",
                        "description": "Know the dancing lights and faerie fire cantrips.",
                    },
                },
            },
        ),
    ],
    race_service: SubraceFeaturesDep,
    _: GmUserDep,
):
    """
    Update one feature of a subrace in place. **GM only.**

    The feature keeps its id, so character grants and any player notes on
    them survive. Only `name`, `level`, `description` are
    editable; omitted fields are left as-is. Returns the updated
    feature.
    """

    return await race_service.update_feature(race_id, subrace_id, feature_id, data)


@router.delete(
    "/features",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a feature from a subrace",
    responses={
        400: {"description": "The feature belongs to a different subrace."},
        404: {
            "description": "No subrace exists with the given ID under this race, or no feature exists with the given ID."
        },
    },
)
async def remove_feature(
    race_id: Annotated[int, Query(gt=0)],
    subrace_id: Annotated[int, Query(gt=0)],
    feature_id: Annotated[int, Query(gt=0)],
    race_service: SubraceFeaturesDep,
    _: GmUserDep,
):
    """
    Remove one feature from a subrace. **GM only.**

    Deletes the feature, cascading away any `CharacterFeature` grants on
    it, and reconciles the affected characters in the same transaction.
    """

    await race_service.remove_feature(race_id, subrace_id, feature_id)
    return None
