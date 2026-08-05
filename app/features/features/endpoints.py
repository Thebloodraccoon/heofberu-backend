"""Feature endpoints: listing, CRUD, and source-consistent filtering."""

from fastapi import APIRouter, Body, Query

from app.constants import FeatureSourceType
from app.core.base_service import Page
from app.core.dependencies import FeatureServiceDep, GmUserDep
from app.features.features.schemas import FeatureBriefResponse, FeatureCreate, FeatureResponse, FeatureUpdate

router = APIRouter(prefix="/features", tags=["Features"])


@router.get(
    "/",
    response_model=Page[FeatureResponse],
    summary="List features (full detail, filterable)",
)
def get_features(
    feature_service: FeatureServiceDep,
    source_type: FeatureSourceType | None = None,
    class_id: int | None = None,
    race_id: int | None = None,
    background_id: int | None = None,
    feat_id: int | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
):
    """
    Return a paginated list of features, with full detail, ordered by
    id.

    Open endpoint, no authentication required.

    All filters are optional and ANDed together when combined, e.g.
    `?source_type=CLASS&class_id=5` returns only class features for
    class 5. Omitting a filter means "don't restrict on this field" — use
    `class_id=5` alone to get every feature tied to that class regardless
    of source_type (relevant since CLASS and SUBCLASS features both key
    off `class_id`).

    `search` is a case-insensitive partial match against the features name.

    Response is `{items, total, page, size}` — `total` is the count of
    matching features across every page, not just this one.

    For a lighter payload, use `GET /features/brief` instead.
    """

    filters = {
        "source_type": source_type,
        "class_id": class_id,
        "race_id": race_id,
        "background_id": background_id,
        "feat_id": feat_id,
    }
    return feature_service.get_all(page=page, size=size, filters=filters, search=search)


@router.get(
    "/brief",
    response_model=Page[FeatureBriefResponse],
    summary="List features (minimal fields, filterable)",
)
def get_features_brief(
    feature_service: FeatureServiceDep,
    source_type: FeatureSourceType | None = None,
    class_id: int | None = None,
    race_id: int | None = None,
    background_id: int | None = None,
    feat_id: int | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
):
    """
    Return a paginated list of features with only `id`, `name`,
    `source_type`, `class_id`, `race_id`, `background_id`, `feat_id`,
    `level`, and `is_homebrew`.

    Open endpoint, no authentication required.

    `search` is a case-insensitive partial match against the features name.

    Response is `{items, total, page, size}`, same shape as `GET /features/`.

    Same filters as `GET /features/`. Does not include the description —
    use `GET /features/{feature_id}` for the full record. Intended for
    dropdowns, tables, and similar listing UI where the full payload is
    unnecessary.
    """

    filters = {
        "source_type": source_type,
        "class_id": class_id,
        "race_id": race_id,
        "background_id": background_id,
        "feat_id": feat_id,
    }
    return feature_service.list_brief(page=page, size=size, filters=filters, search=search)


@router.get(
    "/{feature_id}",
    response_model=FeatureResponse,
    summary="Get a feature by ID",
    responses={
        404: {"description": "Feature with id not found."},
    },
)
def get_feature(feature_id: int, feature_service: FeatureServiceDep):
    """
    Return a single feature by ID, with full detail.

    Open endpoint, no authentication required.
    """
    return feature_service.get_by_id(feature_id)


@router.post(
    "/",
    response_model=FeatureResponse,
    status_code=201,
    summary="Create a feature",
    responses={
        400: {
            "description": (
                "source_type/class_id/race_id/background_id/feat_id/level/subclass_name "
                "combination is inconsistent — see FeatureBase's validator."
            )
        },
    },
)
def create_feature(
    feature_service: FeatureServiceDep,
    _: GmUserDep,
    feature_data: FeatureCreate = Body(
        openapi_examples={
            "class_feature": {
                "summary": "Class feature (e.g. Extra Attack)",
                "value": {
                    "name": "Extra Attack",
                    "source_type": "CLASS",
                    "class_id": 3,
                    "level": 5,
                    "description": "You can attack twice, instead of once, whenever you take the Attack action on your turn.",
                },
            },
            "subclass_feature": {
                "summary": "Subclass feature",
                "value": {
                    "name": "Improved Critical",
                    "source_type": "SUBCLASS",
                    "class_id": 3,
                    "level": 3,
                    "subclass_name": "Champion",
                    "description": "Your weapon attacks score a critical hit on a roll of 19 or 20.",
                },
            },
            "racial_trait": {
                "summary": "Racial trait",
                "value": {
                    "name": "Darkvision",
                    "source_type": "RACE",
                    "race_id": 2,
                    "description": "You can see in dim light within 60 feet of you as if it were bright light.",
                },
            },
            "feat": {
                "summary": "Feat benefit (references a Feat record)",
                "value": {
                    "name": "Alert",
                    "source_type": "FEAT",
                    "feat_id": 1,
                    "description": "You gain a +5 bonus to initiative and can't be surprised while conscious.",
                },
            },
        },
    ),
):
    """
    Create a new feature. **GM only.**

    `source_type` determines which FK is required:
    - `CLASS` / `SUBCLASS` -> `class_id` required (`SUBCLASS` also expects
      `subclass_name`); `level` is meaningful for both.
    - `RACE` -> `race_id` required.
    - `BACKGROUND` -> `background_id` required.
    - `FEAT` -> `feat_id` required, referencing the granting `Feat`.
    - `OTHER` -> none of `class_id`/`race_id`/`background_id`/`feat_id`
      may be set.

    Setting a FK that doesn't match `source_type` (or omitting the one
    that does) is rejected with a 422 validation error at the schema layer.
    """
    return feature_service.create(feature_data)


@router.patch(
    "/{feature_id}",
    response_model=FeatureResponse,
    summary="Update a feature",
    responses={
        400: {"description": "Resulting source_type/FK combination would be inconsistent."},
        404: {"description": "No feature exists with the given ID."},
    },
)
def update_feature(feature_id: int, update_data: FeatureUpdate, feature_service: FeatureServiceDep, _: GmUserDep):
    """
    Partially update a feature. **GM only.**

    Only fields included in the request body are changed; omitted fields
    are left as-is. If `source_type` is changed, the matching FK
    (`class_id`/`race_id`/`background_id`/`feat_id`) must be included
    explicitly in the same request — the previous FK is not carried over
    automatically, to avoid leaving a stale reference from the old
    source_type.
    """
    return feature_service.update_feature(feature_id, update_data)


@router.delete(
    "/{feature_id}",
    status_code=204,
    summary="Delete a feature",
    responses={
        404: {"description": "No feature exists with the given ID."},
    },
)
def delete_feature(feature_id: int, feature_service: FeatureServiceDep, _: GmUserDep):
    """
    Delete a feature. **GM only.**

    Also removes any `CharacterFeature` rows referencing it (cascade).
    """
    feature_service.delete(feature_id)
    return None
