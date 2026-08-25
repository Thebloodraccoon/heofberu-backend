"""
Subclass feature endpoints: per-subclass SUBCLASS-source feature CRUD
(query-style IDs).

The router declares no prefix of its own;
``app.features.classes.router`` applies the ``/classes`` prefix and
``app.features.classes.subclasses.router`` the static ``/subclasses``
prefix — combined, ``"/features"`` resolves to
``/classes/subclasses/features?class_id=...&subclass_id=...``. Both the
owning class and the subclass are identified by required query
parameters.
"""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.features.classes.subclasses.dependencies import SubclassFeaturesDep
from app.features.classes.subclasses.features.schemas import FeatureUpdate, NestedFeatureCreate, NestedFeatureResponse
from app.features.users.security import GmUserDep

router = APIRouter()


@router.get(
    "/features",
    response_model=list[NestedFeatureResponse],
    summary="List a subclass's features",
    responses={404: {"description": "Class or subclass not found."}},
)
async def list_subclass_features(
    class_id: Annotated[int, Query(gt=0)],
    subclass_id: Annotated[int, Query(gt=0)],
    class_service: SubclassFeaturesDep,
):
    """Return every SUBCLASS-source feature of the subclass. Open endpoint."""

    return await class_service.list_features(class_id, subclass_id)


@router.post(
    "/features",
    response_model=NestedFeatureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a feature to a subclass",
    responses={
        404: {"description": "Class or subclass not found."},
    },
)
async def add_subclass_feature(
    class_id: Annotated[int, Query(gt=0)],
    subclass_id: Annotated[int, Query(gt=0)],
    data: Annotated[
        NestedFeatureCreate,
        Body(
            openapi_examples={
                "improved_critical": {
                    "summary": "Add one subclass feature",
                    "value": {
                        "name": "Improved Critical",
                        "level": 3,
                        "description": "Your weapon attacks score a critical hit on a roll of 19 or 20.",
                    },
                },
            },
        ),
    ],
    class_service: SubclassFeaturesDep,
    current_user: GmUserDep,
):
    """
    Add one feature to a subclass. **GM only.**

    The feature is created with ``source_type: SUBCLASS`` and becomes an
    auto-grant for every character holding this subclass (level-gated) in
    the same transaction. Returns the created feature.
    """

    return await class_service.add_feature(class_id, subclass_id, data)


@router.patch(
    "/features",
    response_model=NestedFeatureResponse,
    summary="Update one feature of a subclass",
    responses={
        400: {"description": "The feature belongs to a different subclass, or the update is invalid."},
        404: {"description": "Class or subclass not found, or no feature exists with the given ID."},
    },
)
async def update_subclass_feature(
    class_id: Annotated[int, Query(gt=0)],
    subclass_id: Annotated[int, Query(gt=0)],
    feature_id: Annotated[int, Query(gt=0)],
    data: Annotated[
        FeatureUpdate,
        Body(
            openapi_examples={
                "rename": {
                    "summary": "Edit one feature",
                    "value": {
                        "name": "Improved Critical (Master)",
                        "level": 3,
                        "description": "Your weapon attacks score a critical hit on a roll of 19 or 20.",
                    },
                },
            },
        ),
    ],
    class_service: SubclassFeaturesDep,
    _: GmUserDep,
):
    """
    Update one feature of a subclass in place. **GM only.**

    The feature keeps its id, so character grants and any player notes on
    them survive. Only `name`, `level`, `description` are
    editable; omitted fields are left as-is. Raising a feature's
    `level` revokes it from characters below the new level. Returns the
    updated feature.
    """

    return await class_service.update_feature(class_id, subclass_id, feature_id, data)


@router.delete(
    "/features",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a feature from a subclass",
    responses={
        400: {"description": "The feature belongs to a different subclass."},
        404: {"description": "Class or subclass not found, or no feature exists with the given ID."},
    },
)
async def remove_subclass_feature(
    class_id: Annotated[int, Query(gt=0)],
    subclass_id: Annotated[int, Query(gt=0)],
    feature_id: Annotated[int, Query(gt=0)],
    class_service: SubclassFeaturesDep,
    _: GmUserDep,
):
    """
    Remove one feature from a subclass. **GM only.**

    Deletes the feature, cascading away any `CharacterFeature` grants on
    it, and reconciles the affected characters in the same transaction.
    """

    await class_service.remove_feature(class_id, subclass_id, feature_id)
    return None
