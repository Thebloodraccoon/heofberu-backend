"""Central feature CRUD endpoints: list, get, create, update, delete — for every source type."""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.constants import FeatureSourceType
from app.core.base.service import Page
from app.features.features.crud.schemas import (
    FeatureCreate,
    FeatureGetAllResponse,
    FeatureResponse,
    FeatureUpdate,
)
from app.features.features.dependencies import FeatureCrudDep
from app.features.users.security import GmUserDep

router = APIRouter()

@router.get(
    "",
    response_model=Page[FeatureGetAllResponse],
    summary="List standalone features",
)
async def get_features(
    feature_service: FeatureCrudDep,
    search: str | None = Query(
        None,
        description="Case-insensitive substring match against the feature's name.",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
):
    """
    Return a paginated list of standalone (``source_type: OTHER``) features
    with only `id`, `name`, `source_type`, `level`. Source-owned features
    are listed through their parent record.
    Open endpoint.
    """

    return await feature_service.get_all(
        page=page,
        size=size,
        filters={"source_type": FeatureSourceType.OTHER},
        search=search,
    )

@router.get(
    "/{feature_id:int}",
    response_model=FeatureResponse,
    summary="Get a feature by ID",
    responses={
        404: {"description": "No feature exists with the given ID."},
    },
)
async def get_feature(feature_id: int, feature_service: FeatureCrudDep):
    """
    Return a single feature, with full detail, of every source type —
    standalone ``OTHER`` features and source-owned features alike.
    Open endpoint.
    """

    return await feature_service.get_by_id(feature_id)

@router.post(
    "",
    response_model=FeatureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a feature",
    responses={
        400: {
            "description": (
                "source_type/class_id/subclass_id/race_id/background_id/level "
                "combination is inconsistent — see FeatureBase's validator."
            )
        },
    },
)
async def create_feature(
    data: Annotated[
        FeatureCreate,
        Body(
            openapi_examples={
                "custom_feature": {
                    "summary": "Standalone homebrew feature",
                    "value": {
                        "name": "Bond of the Ancient Oath",
                        "source_type": "OTHER",
                        "description": "A GM-crafted feature granted to a character at the table.",
                    },
                },
            },
        ),
    ],
    feature_service: FeatureCrudDep,
    _: GmUserDep,
):
    """
    Create a feature of any source type. **GM only.**

    Pass ``source_type`` plus the matching parent FK to create a source-owned
    feature, or ``source_type: OTHER`` with no FK for a standalone feature.
    `level` is mandatory for CLASS/SUBCLASS features; mismatched
    source_type/FK/level combinations are rejected with a 422.
    """

    return await feature_service.create(data)

@router.patch(
    "/{feature_id:int}",
    response_model=FeatureResponse,
    summary="Update a feature",
    responses={
        400: {
            "description": (
                "The patch would leave a CLASS/SUBCLASS feature without its "
                "mandatory 'level' (or with a level outside 1-20)."
            )
        },
        404: {"description": "No feature exists with the given ID."},
    },
)
async def update_feature(
    feature_id: int,
    data: Annotated[
        FeatureUpdate,
        Body(
            openapi_examples={
                "rename": {
                    "summary": "Rename the feature and edit its description",
                    "value": {
                        "name": "Bond of the Ancient Oath",
                        "description": "A GM-crafted feature granted to a character at the table.",
                    },
                },
            }
        ),
    ],
    feature_service: FeatureCrudDep,
    _: GmUserDep,
):
    """
    Partially update a feature of any source type. **GM only.**

    Only provided fields are changed; `source_type` and its FK are immutable.
    A CLASS/SUBCLASS feature's `level` may be changed but never cleared.
    """

    return await feature_service.update_feature(feature_id, data)

@router.delete(
    "/{feature_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a feature",
    responses={
        404: {"description": "No feature exists with the given ID."},
    },
)
async def delete_feature(feature_id: int, feature_service: FeatureCrudDep, _: GmUserDep):
    """
    Delete a feature of any source type. **GM only.**

    Also removes any `CharacterFeature` rows referencing it (cascade).
    """

    await feature_service.delete(feature_id)
    return None
