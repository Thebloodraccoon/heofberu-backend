"""Background endpoints: BACKGROUND-source feature management."""

from fastapi import APIRouter, Body

from app.core.security.dependencies import GmUserDep
from app.features.backgrounds.dependencies import BackgroundFeaturesDep
from app.features.backgrounds.features.schemas import FeatureUpdate, NestedFeatureCreate, NestedFeatureResponse

router = APIRouter()


@router.get(
    "/{background_id}/features",
    response_model=list[NestedFeatureResponse],
    summary="List a background's features",
    responses={404: {"description": "No background exists with the given ID."}},
)
async def list_background_features(background_id: int, background_service: BackgroundFeaturesDep):
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
    background_service: BackgroundFeaturesDep,
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
    background_service: BackgroundFeaturesDep,
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
    them survive. Only `name`, `level`, `description` are
    editable; omitted fields are left as-is. Returns the updated
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
