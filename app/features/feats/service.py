"""Feat CRUD service including ASI-choice management."""

from sqlalchemy.orm import Session

from app.core.base_service import BaseService
from app.features.feats.repository import FeatRepository
from app.features.feats.schemas import (
    AbilityScoreIncreasesUpdate,
    FeatBriefResponse,
    FeatCreate,
    FeatResponse,
    FeatUpdate,
)
from app.models.feat_model import Feat


class FeatService(BaseService[Feat, FeatCreate, FeatUpdate, FeatResponse, FeatBriefResponse]):
    """
    Feat-specific CRUD service built on :class:`BaseService`.

    Mirrors ``RaceService``: a uniqueness check on ``name`` before
    create/update, management of ``ability_score_increases`` (its own
    child table, no generic base-class equivalent, set up in the same
    transaction as the feat via ``BaseService._atomic()``), and a delete
    guard blocking removal of a feat still granted to any character or
    referenced by a Feature.
    """

    repository: FeatRepository

    def __init__(self, db: Session):
        super().__init__(
            repository=FeatRepository(db),
            response_schema=FeatResponse,
            brief_schema=FeatBriefResponse,
        )

    def create_feat(self, feat_data: FeatCreate, created_by_id: int | None = None) -> FeatResponse:
        """
        Create a feat after checking its name isn't already taken.

        ``feat_data.ability_score_increases`` is optional. If supplied,
        it's set in the same transaction as the feat itself via
        ``BaseService._atomic()`` — same reasoning as
        ``RaceService.create_race``.
        """

        payload = feat_data.model_dump(exclude={"ability_score_increases"})
        payload["created_by_id"] = created_by_id

        with self._atomic():
            item = self.repository.create(payload, commit=False)

            if feat_data.ability_score_increases:
                increases = [
                    {"ability": inc.ability, "amount": inc.amount} for inc in feat_data.ability_score_increases
                ]
                self.repository.set_ability_score_increases(item, increases, commit=False)

        self.repository.refresh(item)
        return self.response_schema.model_validate(item)

    def set_ability_score_increases(self, feat_id: int, data: AbilityScoreIncreasesUpdate) -> FeatResponse:
        """Fully replace a feat's ASI choices."""

        feat = self._get_or_404(feat_id)

        increases = [{"ability": item.ability, "amount": item.amount} for item in data.ability_score_increases]
        updated_feat = self.repository.set_ability_score_increases(feat, increases)
        return self.response_schema.model_validate(updated_feat)
