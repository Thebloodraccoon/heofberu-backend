"""Feature CRUD service with source_type/FK consistency re-validation."""

from sqlalchemy.orm import Session

from app.constants import FeatureSourceType
from app.core.base_service import BaseService
from app.features.features.exceptions import InvalidFeatureSourceException
from app.features.features.repository import FeatureRepository
from app.features.features.schemas import (
    _REQUIRED_FK_BY_SOURCE_TYPE,
    FeatureBriefResponse,
    FeatureCreate,
    FeatureResponse,
    FeatureUpdate,
    NestedFeatureCreate,
    _validate_source_fk_consistency,
)
from app.models.feature_model import Feature


def create_features_for_source(
    db: Session,
    source_type: FeatureSourceType,
    source_id: int,
    items: list[NestedFeatureCreate] | None,
    created_by_id: int | None,
    *,
    commit: bool = False,
) -> list[Feature]:
    """
    Create ``Feature`` rows attached to a source record inside an open transaction.

    Called by race/class/background/feat/subclass create services so a client
    can supply features up front in the same request that creates the source.

    Args:
        db: Active session — must already be inside the caller's
            ``_atomic()`` block so rows share the parent transaction.
        source_type: Which source the features belong to. Determines the FK
            column that gets set (CLASS→class_id, SUBCLASS→subclass_id, ...).
        source_id: ID of the owning record.
        items: Nested feature payloads. ``None`` or empty returns ``[]``.
        created_by_id: Optional GM id stored on each created feature.
        commit: Pass ``False`` when called from within ``_atomic()``.

    Returns:
        The created ``Feature`` model instances.
    """
    if not items:
        return []

    fk_name = _REQUIRED_FK_BY_SOURCE_TYPE[source_type]
    if fk_name is None:
        raise ValueError(f"source_type='{source_type.value}' has no source FK; nested creation is not supported.")

    repository = FeatureRepository(db)
    created: list[Feature] = []

    for item in items:
        payload = item.model_dump()
        payload["source_type"] = source_type
        payload[fk_name] = source_id
        feature = FeatureCreate(**payload)  # re-runs source_type/FK consistency validator
        created.append(repository.create(feature.model_dump(), commit=commit))

    return created


class FeatureService(BaseService[Feature, FeatureCreate, FeatureUpdate, FeatureResponse, FeatureBriefResponse]):
    """
    Feature-specific CRUD service built on :class:`BaseService`.

    Adds:
      - filtered listing by source_type/class_id/subclass_id/race_id/
        background_id/feat_id via the generic ``filters`` dict;
      - re-validation of source_type/FK consistency on PATCH update, since
        ``FeatureUpdate`` is partial and can't validate the combination on
        its own — the service merges incoming fields onto the existing record
        and re-checks via ``_validate_source_fk_consistency``.
    """

    repository: FeatureRepository

    def __init__(self, db: Session):
        super().__init__(
            repository=FeatureRepository(db),
            response_schema=FeatureResponse,
            brief_schema=FeatureBriefResponse,
        )

    def update_feature(self, feature_id: int, update_data: FeatureUpdate) -> FeatureResponse:
        """
        Update a feature, re-validating source_type/FK consistency against
        the merged (existing + incoming) state.
        """

        feature = self._get_or_404(feature_id)
        fields = update_data.model_dump(exclude_unset=True)

        source_type_changing = "source_type" in fields

        def merged_value(fk_name: str):
            if fk_name in fields:
                return fields[fk_name]
            if source_type_changing:
                return None
            return getattr(feature, fk_name, None)

        merged = {
            "source_type": fields.get("source_type", feature.source_type),
            "class_id": merged_value("class_id"),
            "subclass_id": merged_value("subclass_id"),
            "race_id": merged_value("race_id"),
            "background_id": merged_value("background_id"),
            "feat_id": merged_value("feat_id"),
            "level": fields.get("level", feature.level),
            "subclass_name": fields.get("subclass_name", feature.subclass_name),
        }

        try:
            _validate_source_fk_consistency(merged["source_type"], merged)
        except ValueError as exc:
            raise InvalidFeatureSourceException(str(exc)) from exc

        updated_feature = self.repository.update(feature, fields)
        return self.response_schema.model_validate(updated_feature)
