"""
Class feature endpoints: per-feature CRUD for CLASS-source features
(query-style ID — the class is identified by the required ``class_id``
query parameter).
"""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.features.classes.dependencies import ClassFeaturesDep
from app.features.shared.features.schemas import FeatureUpdate, NestedFeatureCreate, NestedFeatureResponse
from app.features.users.security import GmUserDep

router = APIRouter()


@router.get(
    "/features",
    response_model=list[NestedFeatureResponse],
    summary="List a class's features",
    responses={404: {"description": "No class exists with the given ID."}},
)
async def list_class_features(class_id: Annotated[int, Query(gt=0)], class_service: ClassFeaturesDep):
    """Return every CLASS-source feature of the class. Open endpoint."""

    return await class_service.list_features(class_id)


@router.post(
    "/features",
    response_model=NestedFeatureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a feature to a class",
    responses={
        404: {"description": "No class exists with the given ID."},
    },
)
async def add_class_feature(
    class_id: Annotated[int, Query(gt=0)],
    data: Annotated[
        NestedFeatureCreate,
        Body(
            openapi_examples={
                "second_wind": {
                    "summary": "Add one class feature",
                    "value": {
                        "name": "Second Wind",
                        "level": 1,
                        "description": "Regain HP as a bonus action.",
                    },
                },
            },
        ),
    ],
    class_service: ClassFeaturesDep,
    current_user: GmUserDep,
):
    """
    Add one feature to a class. **GM only.**

    The feature is created with ``source_type: CLASS`` and becomes an
    auto-grant for every character of this class (level-gated) in the same
    transaction. Returns the created feature.
    """

    return await class_service.add_feature(class_id, data, created_by_id=current_user.id)


@router.patch(
    "/features",
    response_model=NestedFeatureResponse,
    summary="Update one feature of a class",
    responses={
        400: {"description": "The feature belongs to a different class, or the update is invalid."},
        404: {"description": "No class exists with the given ID, or no feature exists with the given ID."},
    },
)
async def update_class_feature(
    class_id: Annotated[int, Query(gt=0)],
    feature_id: Annotated[int, Query(gt=0)],
    data: Annotated[
        FeatureUpdate,
        Body(
            openapi_examples={
                "rename": {
                    "summary": "Edit one feature",
                    "value": {
                        "name": "Improved Second Wind",
                        "level": 1,
                        "description": "Regain more HP as a bonus action.",
                    },
                },
            },
        ),
    ],
    class_service: ClassFeaturesDep,
    _: GmUserDep,
):
    """
    Update one feature of a class in place. **GM only.**

    The feature keeps its id, so character grants and any player notes on
    them survive. Only `name`, `level`, `description` are
    editable; omitted fields are left as-is. Raising a feature's
    `level` revokes it from characters below the new level. Returns the
    updated feature.
    """

    return await class_service.update_feature(class_id, feature_id, data)


@router.delete(
    "/features",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a feature from a class",
    responses={
        400: {"description": "The feature belongs to a different class."},
        404: {"description": "No class exists with the given ID, or no feature exists with the given ID."},
    },
)
async def remove_class_feature(
    class_id: Annotated[int, Query(gt=0)],
    feature_id: Annotated[int, Query(gt=0)],
    class_service: ClassFeaturesDep,
    _: GmUserDep,
):
    """
    Remove one feature from a class. **GM only.**

    Deletes the feature, cascading away any `CharacterFeature` grants on
    it, and reconciles the affected characters in the same transaction.
    """

    await class_service.remove_feature(class_id, feature_id)
    return None
