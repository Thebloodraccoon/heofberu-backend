"""Background tags service: full replacement and id resolution."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.backgrounds.cache import BACKGROUND_CACHE_NAMESPACES
from app.features.backgrounds.crud.schemas import BackgroundCreate, BackgroundResponse, BackgroundUpdate
from app.features.backgrounds.tags.repository import BackgroundTagsRepository
from app.features.shared.tags.mixins import TagsManagerMixin
from app.models.backgrounds.background_model import Background


class BackgroundTagService(
    TagsManagerMixin,
    BaseService[Background, BackgroundCreate, BackgroundUpdate, BackgroundResponse, None],
):
    """Full replacement and id-resolution for a background's tags."""

    repository: BackgroundTagsRepository

    cache_namespaces = BACKGROUND_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize with a background tags repository and the background response schema."""

        super().__init__(
            repository=BackgroundTagsRepository(db),
            response_schema=BackgroundResponse,
        )
