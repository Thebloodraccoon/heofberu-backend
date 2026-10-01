"""Race ability-bonus service: full replacement of a race's bonuses."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.features.characters.progression.source_bonuses import AbilityBonusesManagerMixin
from app.features.races.cache import RACE_CACHE_NAMESPACES
from app.features.races.crud.repository import RaceRepository
from app.features.races.crud.schemas import RaceCreate, RaceResponse, RaceUpdate
from app.features.shared.catalog.cache import CatalogCacheMixin
from app.models.races.race_model import Race


class RaceAbilityBonusService(
    AbilityBonusesManagerMixin,
    CatalogCacheMixin,
    BaseService[Race, RaceCreate, RaceUpdate, RaceResponse, None],
):
    """Full replacement of a race's ability score bonuses."""

    repository: RaceRepository

    cache_namespaces = RACE_CACHE_NAMESPACES
    _bonus_source_type = FeatureSourceType.RACE

    def __init__(self, db: AsyncSession):
        """Initialize with a race repository and the race response schema."""

        super().__init__(
            repository=RaceRepository(db),
            response_schema=RaceResponse,
        )
