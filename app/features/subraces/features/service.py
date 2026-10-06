"""Subrace feature service: read-only, cached listing for SUBRACE-source features."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.features.features.crud.source_features import SourceFeaturesService
from app.features.subraces.crud.repository import SubraceRepository


class SubraceFeatureService(SourceFeaturesService):
    """Cached listing of the SUBRACE-source features of a subrace."""

    cache_namespaces = ("subrace_features",)
    source_type = FeatureSourceType.SUBRACE
    model_name = "Subrace"

    def __init__(self, db: AsyncSession):
        """Initialize with a subrace repository and a composed feature reader."""

        super().__init__(SubraceRepository(db), db)
