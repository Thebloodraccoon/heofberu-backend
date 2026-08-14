"""Feature CRUD endpoints: standalone (OTHER) listing, get, create, update, delete."""

from fastapi import APIRouter, Body, Query

from app.constants import FeatureSourceType
from app.core.base.service import Page
from app.core.security.dependencies import GmUserDep
from app.features.features.crud.schemas import (
    FeatureGetAllResponse,
    FeatureResponse,
    StandaloneFeatureCreate,
)
from app.features.features.dependencies import FeatureCrudDep
from app.features.shared.features.schemas import FeatureUpdate

router = APIRouter()


@router.get(
    "",
    response_model=Page[FeatureGetAllResponse],
    summary="List standalone features",
)
async def get_features(
    feature_service: FeatureCrudDep,
    search: str | None = None,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
):
    """
    Return a paginated list of standalone (``source_type: OTHER``) features
    with only `id`, `name`, `source_type`, `level`.

    Open endpoint, no authentication required.

    Features owned by a class/race/background/feat/subclass are NOT
    included — they live under their parent record
    (`GET /races/{id}`, `GET /classes/{id}`, ...) and are managed through
    that parent's per-feature endpoints.

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
    "/{feature_id}",
    response_model=FeatureResponse,
    summary="Get a standalone feature by ID",
    responses={
        404: {"description": "Feature with id not found, or the feature is owned by a parent record."},
    },
)
async def get_feature(feature_id: int, feature_service: FeatureCrudDep):
    """
    Return a single standalone (``source_type: OTHER``) feature, with full
    detail.

    Open endpoint, no authentication required.

    Only standalone features are served here — a class/race/background/
    feat/subclass feature returns 404, since those live under their parent
    record.
    """

    return await feature_service.get_standalone(feature_id)


@router.post(
    "",
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
    feature_service: FeatureCrudDep,
    _: GmUserDep,
    feature_data: StandaloneFeatureCreate = Body(
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
):
    """
    Create a standalone feature. **GM only.**

    Only ``source_type: OTHER`` is accepted here — a standalone feature
    owned by no parent record, which the GM can then grant to any
    character.

    Class, subclass, race, background and feat features are owned by
    their parent records: they are created through that parent's nested
    ``features`` payload (``POST /races/``, ``POST /classes/``,
    ``POST /backgrounds/``, ``POST /feats/``, ...) or added one-by-one via
    ``POST /{source}/{id}/features`` — and must NOT be posted here (422).

    None of ``class_id``/``subclass_id``/``race_id``/``background_id``/
    ``feat_id`` may be set. ``level`` is optional and meaningful for
    CLASS/SUBCLASS/OTHER features.
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
                "managed through their parent's per-feature endpoints; or the resulting "
                "source_type/FK combination would be inconsistent."
            )
        },
        404: {"description": "No feature exists with the given ID."},
    },
)
async def update_feature(feature_id: int, update_data: FeatureUpdate, feature_service: FeatureCrudDep, _: GmUserDep):
    """
    Partially update a standalone feature. **GM only.**

    Only ``source_type: OTHER`` (standalone) features are editable here —
    class/subclass/race/background/feat features are owned by their parent
    record and are managed through the parent's per-feature endpoints.

    Only fields included in the request body are changed; omitted fields
    are left as-is.

    `source_type` and its FK are immutable — ownership never moves. Only
    `name`, `level`, `description` are editable. Setting
    a non-`None` `level` on a feature that isn't CLASS/SUBCLASS/OTHER is
    rejected with a 400.
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
                "managed through their parent's per-feature endpoints."
            )
        },
        404: {"description": "No feature exists with the given ID."},
    },
)
async def delete_feature(feature_id: int, feature_service: FeatureCrudDep, _: GmUserDep):
    """
    Delete a standalone feature. **GM only.**

    Only ``source_type: OTHER`` (standalone) features can be deleted
    here — class/subclass/race/background/feat features are deleted
    through their parent's per-feature endpoints.

    Also removes any `CharacterFeature` rows referencing it (cascade).
    """

    await feature_service.delete(feature_id)
    return None
