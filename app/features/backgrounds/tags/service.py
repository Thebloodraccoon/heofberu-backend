"""Background tags service: full replacement and id resolution."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.backgrounds.capability import BackgroundCapabilityService
from app.features.backgrounds.tags.repository import BackgroundTagsRepository
from app.features.shared.tags.mixins import TagsManagerMixin


class BackgroundTagService(TagsManagerMixin, BackgroundCapabilityService):
    """Full replacement of a background's tags; ``set_tags`` comes from :class:`TagsManagerMixin`."""

    repository: BackgroundTagsRepository

    def __init__(self, db: AsyncSession):
        """Initialize with a background tags repository."""

        super().__init__(BackgroundTagsRepository(db))
