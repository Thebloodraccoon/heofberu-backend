"""Background granted-skill service: full replacement."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.backgrounds.capability import BackgroundCapabilityService
from app.features.backgrounds.skills.repository import BackgroundSkillsRepository
from app.features.shared.skills.mixins import SkillsManagerMixin


class BackgroundSkillsService(SkillsManagerMixin, BackgroundCapabilityService):
    """Background granted skills; ``set_skills`` comes from :class:`SkillsManagerMixin`."""

    repository: BackgroundSkillsRepository

    def __init__(self, db: AsyncSession):
        """Initialize the service with the skills repository."""

        super().__init__(BackgroundSkillsRepository(db))
