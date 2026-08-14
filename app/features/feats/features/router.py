from fastapi import APIRouter, Body

from app.core.security.dependencies import GmUserDep
from app.features.feats.dependencies import FeatFeaturesDep
from app.features.shared.features.schemas import FeatureUpdate, NestedFeatureCreate, NestedFeatureResponse

router = APIRouter()


@router.get(
    "/{feat_id}/features",
    response_model=list[NestedFeatureResponse],
    summary="List a feat's features",
    responses={404: {"description": "No feat exists with the given ID."}},
)
async def list_feat_features(feat_id: int, feat_service: FeatFeaturesDep):
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
    feat_service: FeatFeaturesDep,
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
    feat_service: FeatFeaturesDep,
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
    them survive. Only `name`, `level`, `description` are
    editable; omitted fields are left as-is. Returns the updated
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
    feat_service: FeatFeaturesDep,
    _: GmUserDep,
):
    """
    Remove one feature from a feat. **GM only.**

    Deletes the feature, cascading away any `CharacterFeature` grants on
    it, and reconciles the affected characters in the same transaction.
    """

    await feat_service.remove_feature(feat_id, feature_id)
    return None
