from sqlalchemy.orm import Session

from app.constants import FeatureSourceType
from app.core.base_repository import BaseRepository
from app.models.feature_model import Feature


class FeatureRepository(BaseRepository[Feature]):
    def __init__(self, db: Session):
        super().__init__(Feature, db)

    def get_filtered(
        self,
        *,
        source_type: FeatureSourceType | None = None,
        class_id: int | None = None,
        race_id: int | None = None,
        background_id: int | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Feature]:
        """
        Return features matching the given filters (all optional, ANDed
        together), ordered by name, with pagination.

        Only filters that are not ``None`` are applied — omitting a filter
        means "don't restrict on this field", not "field IS NULL".
        """

        query = self.db.query(Feature)

        if source_type is not None:
            query = query.filter(Feature.source_type == source_type)
        if class_id is not None:
            query = query.filter(Feature.class_id == class_id)
        if race_id is not None:
            query = query.filter(Feature.race_id == race_id)
        if background_id is not None:
            query = query.filter(Feature.background_id == background_id)

        return query.order_by(Feature.name).offset(skip).limit(limit).all()
