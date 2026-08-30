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
    with only `id`, `name`, `source_type`, `level`.

    Open endpoint, no authentication required.

    Features owned by a class/race/background/subclass/subrace are NOT
    included — they are listed through the parent record
    (`GET /races/{id}/features`, `GET /classes/{id}/features`, ...).

    `search` is a case-insensitive partial match against the feature name.

    Response is `{items, total, page, size}` — `total` is the count of
    matching features across every page, not just this one.

    Does not include the description — use `GET /features/{feature_id}`
    for the full record.
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
    Return a single feature, with full detail.

    Open endpoint, no authentication required.

    Serves features of every source type — standalone ``OTHER`` features and
    features owned by a class/subclass/race/subrace/background alike.
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

    Features are managed centrally through this catalog: pass
    ``source_type`` plus the matching parent FK (``class_id``,
    ``subclass_id``, ``race_id``, ``subrace_id``, ``background_id``) to
    create a feature owned by that record, or ``source_type: OTHER`` with no
    FK for a standalone feature the GM can grant to any character.

    ``level`` is mandatory for CLASS/SUBCLASS features (1-20) and optional
    for every other source type. The source_type/FK/level combination is
    validated — mismatches (e.g. ``source_type: CLASS`` without
    ``class_id``) are rejected with a 422.
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

    Only fields included in the request body are changed; omitted fields
    are left as-is.

    `source_type` and its FK are immutable — ownership never moves. Only
    `name`, `level`, `description` are editable. A CLASS/SUBCLASS feature's
    `level` is mandatory (1-20): it may be changed but never cleared; for
    other source types `level` is optional.
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
