"""Race granted-skill service: full replacement of a race's granted skills."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.races.cache import RACE_CACHE_NAMESPACES
from app.features.races.crud.schemas import RaceCreate, RaceResponse, RaceUpdate
from app.features.races.skills.repository import RaceSkillsRepository
from app.features.shared.catalog.cache import CatalogCacheMixin
from app.features.shared.skills.mixins import SkillsManagerMixin
from app.models.races.race_model import Race


class RaceSkillService(
    SkillsManagerMixin,
    CatalogCacheMixin,
    BaseService[Race, RaceCreate, RaceUpdate, RaceResponse],
):
    """Full replacement and id-resolution for a race's granted skills."""

    repository: RaceSkillsRepository

    cache_namespaces = RACE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize with a race skills repository and the race response schema."""

        super().__init__(
            repository=RaceSkillsRepository(db),
            response_schema=RaceResponse,
        )
