"""Feature endpoints: listing, CRUD, and source-consistent filtering."""

from fastapi import APIRouter, Body, Query

from app.constants import FeatureSourceType
from app.core.base_service import Page
from app.core.dependencies import FeatureServiceDep, GmUserDep
from app.features.features.schemas import (
    FeatureGetAllResponse,
    FeatureResponse,
    FeatureUpdate,
    StandaloneFeatureCreate,
)

router = APIRouter(prefix="/features", tags=["Features"])


@router.get(
    "/",
    response_model=Page[FeatureGetAllResponse],
    summary="List features (filterable)",
)
async def get_features(
    feature_service: FeatureServiceDep,
    source_type: FeatureSourceType | None = None,
    class_id: int | None = None,
    subclass_id: int | None = None,
    race_id: int | None = None,
    background_id: int | None = None,
    feat_id: int | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
):
    """
    Return a paginated list of features with only `id`, `name`,
    `source_type`, `class_id`, `subclass_id`, `race_id`,
    `background_id`, `feat_id`, `level`, and `is_homebrew`.

    Open endpoint, no authentication required.

    All filters are optional and ANDed together when combined, e.g.
    `?source_type=CLASS&class_id=5` returns only class features for
    class 5. Omitting a filter means "don't restrict on this field". A
    `source_type=SUBCLASS` filter pairs with `subclass_id`.

    `search` is a case-insensitive partial match against the features name.

    Response is `{items, total, page, size}` — `total` is the count of
    matching features across every page, not just this one.

    Does not include the description — use `GET /features/{feature_id}`
    for the full record.
    """

    filters = {
        "source_type": source_type,
        "class_id": class_id,
        "subclass_id": subclass_id,
        "race_id": race_id,
        "background_id": background_id,
        "feat_id": feat_id,
    }

    return await feature_service.get_all(page=page, size=size, filters=filters, search=search)


@router.get(
    "/{feature_id}",
    response_model=FeatureResponse,
    summary="Get a feature by ID",
    responses={
        404: {"description": "Feature with id not found."},
    },
)
async def get_feature(feature_id: int, feature_service: FeatureServiceDep):
    """
    Return a single feature by ID, with full detail.

    Open endpoint, no authentication required.
    """

    return await feature_service.get_by_id(feature_id)


@router.post(
    "/",
    response_model=FeatureResponse,
    status_code=201,
    summary="Create a standalone feature",
    responses={
        400: {
            "description": (
                "source_type/class_id/subclass_id/race_id/background_id/feat_id/level "
                "combination is inconsistent — see FeatureBase's validator."
            )
        },
    },
)
async def create_feature(
    feature_service: FeatureServiceDep,
    _: GmUserDep,
    feature_data: StandaloneFeatureCreate = Body(
        openapi_examples={
            "custom_feature": {
                "summary": "Standalone homebrew feature",
                "value": {
                    "name": "Bond of the Ancient Oath",
                    "source_type": "OTHER",
                    "description": "A GM-crafted feature granted to a character at the table.",
                    "is_homebrew": True,
                },
            },
        },
    ),
):
    """
    Create a standalone feature. **GM only.**

    Only ``source_type: OTHER`` is accepted here — a standalone feature
    owned by no parent record, which the GM can then grant to any
    character.

    Class, subclass, race, background and feat features are owned by
    their parent records: they are created through that parent's nested
    ``features`` payload (``POST /races/``, ``POST /classes/``,
    ``POST /backgrounds/``, ``POST /feats/``, ...) and must NOT be posted
    here — doing so is rejected with a 422.

    None of ``class_id``/``subclass_id``/``race_id``/``background_id``/
    ``feat_id`` may be set, and ``level`` is not meaningful for OTHER
    features (it is only allowed on CLASS/SUBCLASS features).
    """

    return await feature_service.create(feature_data)


@router.patch(
    "/{feature_id}",
    response_model=FeatureResponse,
    summary="Update a standalone feature",
    responses={
        400: {
            "description": (
                "The feature is not standalone (OTHER) — source-owned features are "
                "managed through their parent's replace endpoint; or the resulting "
                "source_type/FK combination would be inconsistent."
            )
        },
        404: {"description": "No feature exists with the given ID."},
    },
)
async def update_feature(feature_id: int, update_data: FeatureUpdate, feature_service: FeatureServiceDep, _: GmUserDep):
    """
    Partially update a standalone feature. **GM only.**

    Only ``source_type: OTHER`` (standalone) features are editable here —
    class/subclass/race/background/feat features are owned by their parent
    record and are managed through the parent's replace endpoint.

    Only fields included in the request body are changed; omitted fields
    are left as-is.

    `source_type` and its FK are immutable — ownership never moves. Only
    `name`, `level`, `description` and `is_homebrew` are editable. Setting
    a non-`None` `level` on a feature that isn't CLASS/SUBCLASS is rejected
    with a 400.
    """

    return await feature_service.update_feature(feature_id, update_data)


@router.delete(
    "/{feature_id}",
    status_code=204,
    summary="Delete a standalone feature",
    responses={
        400: {
            "description": (
                "The feature is not standalone (OTHER) — source-owned features are "
                "managed through their parent's replace endpoint."
            )
        },
        404: {"description": "No feature exists with the given ID."},
    },
)
async def delete_feature(feature_id: int, feature_service: FeatureServiceDep, _: GmUserDep):
    """
    Delete a standalone feature. **GM only.**

    Only ``source_type: OTHER`` (standalone) features can be deleted
    here — class/subclass/race/background/feat features are deleted
    through their parent's replace endpoint.

    Also removes any `CharacterFeature` rows referencing it (cascade).
    """

    await feature_service.delete(feature_id)
    return None
