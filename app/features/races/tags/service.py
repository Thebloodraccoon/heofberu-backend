"""Race tags service: full replacement and id resolution."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.races.cache import RACE_CACHE_NAMESPACES
from app.features.races.crud.schemas import RaceCreate, RaceResponse, RaceUpdate
from app.features.races.tags.repository import RaceTagsRepository
from app.features.shared.tags.mixins import TagsManagerMixin
from app.models.races.race_model import Race


class RaceTagService(
    TagsManagerMixin,
    BaseService[Race, RaceCreate, RaceUpdate, RaceResponse, None],
):
    """Full replacement and id-resolution for a race's tags."""

    repository: RaceTagsRepository

    cache_namespaces = RACE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize with a race tags repository and the race response schema."""

        super().__init__(
            repository=RaceTagsRepository(db),
            response_schema=RaceResponse,
        )
