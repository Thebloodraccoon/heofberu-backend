from sqlalchemy.orm import Session

from app.core.base_service import BaseService
from app.features.features.exceptions import FeatureNotFoundException, InvalidFeatureSourceException
from app.features.features.repository import FeatureRepository
from app.features.features.schemas import (
    FeatureBriefResponse,
    FeatureCreate,
    FeatureResponse,
    FeatureUpdate,
    _validate_source_fk_consistency,
)
from app.models.feature_model import Feature


class FeatureService(BaseService[Feature, FeatureCreate, FeatureUpdate, FeatureResponse, FeatureBriefResponse]):
    """
    Feature-specific CRUD service built on :class:`BaseService`.

    Adds behaviors the generic base class doesn't provide:
      - filtered listing by source_type/class_id/race_id/background_id
        (``list_filtered``/``list_filtered_brief``), since GM tooling and
        character-building UI both need "all features for class X" /
        "all racial traits for race Y" style queries. These are thin
        named-parameter wrappers around ``BaseService.get_all``/
        ``list_brief``'s generic ``filters`` dict (which in turn reaches
        ``FeatureRepository.get_all``, overridden only to sort by name
        instead of ``id``) — there's no bespoke ``get_filtered`` method
        anymore, exact-match filtering is handled generically;
      - re-validation of source_type/FK consistency on update. ``FeatureCreate``
        already validates this at the schema level (a full record is
        available), but ``FeatureUpdate`` is a partial PATCH payload and
        can't validate the combination on its own — this service merges
        the incoming fields onto the existing record and re-checks
        consistency before persisting, raising ``InvalidFeatureSourceException``
        (mapped to 400) if the result would be inconsistent.

    ``create`` is inherited unchanged from ``BaseService`` — no extra
    setup work is needed beyond what ``FeatureCreate``'s own validator
    already enforces. No custom transaction handling is needed anywhere
    in this service (unlike ``ClassService``/``RaceService``/etc.) since
    ``Feature`` has no association-table relationships to set up
    alongside the base record — every write here is a single repository
    call, so there's no ``self._atomic()`` use site.
    """

    repository: FeatureRepository

    def __init__(self, db: Session):
        super().__init__(
            repository=FeatureRepository(db),
            response_schema=FeatureResponse,
            not_found_exception_factory=lambda feature_id: FeatureNotFoundException(feature_id=feature_id),
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
            return getattr(feature, fk_name)

        merged = {
            "source_type": fields.get("source_type", feature.source_type),
            "class_id": merged_value("class_id"),
            "race_id": merged_value("race_id"),
            "background_id": merged_value("background_id"),
            "level": fields.get("level", feature.level),
            "subclass_name": fields.get("subclass_name", feature.subclass_name),
        }

        try:
            _validate_source_fk_consistency(merged["source_type"], merged)
        except ValueError as exc:
            raise InvalidFeatureSourceException(str(exc)) from exc

        updated_feature = self.repository.update(feature, fields)
        return self.response_schema.model_validate(updated_feature)
