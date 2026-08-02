from sqlalchemy.orm import Session

from app.core.base_repository import BaseRepository
from app.models.feature_model import Feature


class FeatureRepository(BaseRepository[Feature]):
    def __init__(self, db: Session):
        super().__init__(Feature, db, search_fields=["name"])
