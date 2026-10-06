"""Race feature service: read-only, cached listing for RACE-source features."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.features.features.crud.source_features import SourceFeaturesService
from app.features.races.crud.repository import RaceRepository


class RaceFeatureService(SourceFeaturesService):
    """Cached listing of a race's RACE-source features."""

    cache_namespaces = ("race_features",)
    source_type = FeatureSourceType.RACE
    model_name = "Race"

    def __init__(self, db: AsyncSession):
        """Initialize with a race repository and a composed feature reader."""

        super().__init__(RaceRepository(db), db)
