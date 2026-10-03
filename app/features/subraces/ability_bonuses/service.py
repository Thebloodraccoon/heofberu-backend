"""Subrace ability-bonus service: full replacement of a subrace bonuses."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.features.characters.progression.source_bonuses import AbilityBonusesManagerMixin
from app.features.shared.catalog.cache import CatalogCacheMixin
from app.features.subraces.cache import SUBRACE_CACHE_NAMESPACES
from app.features.subraces.crud.repository import SubraceRepository
from app.features.subraces.crud.schemas import SubraceCreate, SubraceResponse, SubraceUpdate
from app.models.races.subrace_model import Subrace


class SubraceAbilityBonusService(
    AbilityBonusesManagerMixin,
    CatalogCacheMixin,
    BaseService[Subrace, SubraceCreate, SubraceUpdate, SubraceResponse],
):
    """Full replacement of a subrace ability score bonuses."""

    repository: SubraceRepository

    cache_namespaces = SUBRACE_CACHE_NAMESPACES
    _bonus_source_type = FeatureSourceType.SUBRACE

    def __init__(self, db: AsyncSession):
        """Initialize with a subrace repository and the subrace response schema."""

        super().__init__(
            repository=SubraceRepository(db),
            response_schema=SubraceResponse,
        )
