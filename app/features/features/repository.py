"""Feature repository: base CRUD with name-based search."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_repository import BaseRepository
from app.models.feature_model import Feature


class FeatureRepository(BaseRepository[Feature]):
    """Feature-specific repository built on :class:`BaseRepository`."""

    def __init__(self, db: AsyncSession):
        super().__init__(Feature, db, search_fields=["name"])
