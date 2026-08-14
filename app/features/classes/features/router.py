"""Class feature endpoints: per-feature CRUD for CLASS-source features."""

from fastapi import APIRouter, Body

from app.core.security.dependencies import GmUserDep
from app.features.classes.dependencies import ClassFeaturesDep
from app.features.shared.features.schemas import FeatureUpdate, NestedFeatureCreate, NestedFeatureResponse

router = APIRouter()


@router.get(
    "/{class_id}/features",
    response_model=list[NestedFeatureResponse],
    summary="List a class's features",
    responses={404: {"description": "No class exists with the given ID."}},
)
async def list_class_features(class_id: int, class_service: ClassFeaturesDep):
    """Return every CLASS-source feature of the class. Open endpoint."""

    return await class_service.list_features(class_id)


@router.post(
    "/{class_id}/features",
    response_model=NestedFeatureResponse,
    status_code=201,
    summary="Add a feature to a class",
    responses={
        404: {"description": "No class exists with the given ID."},
    },
)
async def add_class_feature(
    class_id: int,
    class_service: ClassFeaturesDep,
    _: GmUserDep,
    data: NestedFeatureCreate = Body(
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
):
    """
    Add one feature to a class. **GM only.**

    The feature is created with ``source_type: CLASS`` and becomes an
    auto-grant for every character of this class (level-gated) in the same
    transaction. Returns the created feature.
    """

    return await class_service.add_feature(class_id, data, created_by_id=_.id)


@router.patch(
    "/{class_id}/features/{feature_id}",
    response_model=NestedFeatureResponse,
    summary="Update one feature of a class",
    responses={
        400: {"description": "The feature belongs to a different class, or the update is invalid."},
        404: {"description": "No class exists with the given ID, or no feature exists with the given ID."},
    },
)
async def update_class_feature(
    class_id: int,
    feature_id: int,
    class_service: ClassFeaturesDep,
    _: GmUserDep,
    data: FeatureUpdate = Body(
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
    "/{class_id}/features/{feature_id}",
    status_code=204,
    summary="Remove a feature from a class",
    responses={
        400: {"description": "The feature belongs to a different class."},
        404: {"description": "No class exists with the given ID, or no feature exists with the given ID."},
    },
)
async def remove_class_feature(
    class_id: int,
    feature_id: int,
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
