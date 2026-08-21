"""Background granted-skill service: full replacement and id resolution."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.backgrounds.cache import BACKGROUND_CACHE_NAMESPACES
from app.features.backgrounds.crud.schemas import BackgroundCreate, BackgroundResponse, BackgroundUpdate
from app.features.backgrounds.skills.repository import BackgroundSkillsRepository
from app.features.shared.skills.mixins import SkillsManagerMixin
from app.models import Background, Skill


class BackgroundSkillsService(
    SkillsManagerMixin,
    BaseService[Background, BackgroundCreate, BackgroundUpdate, BackgroundResponse, None],
):
    """
    Everything about a background's granted skills.

    ``set_skills`` (full replacement) and skill-id resolution are inherited
    from :class:`SkillsManagerMixin`; the generic CRUD machinery
    (``_get_or_404``/``_get_response``/``_invalidate_cache``) comes from
    :class:`BaseService`. Any write purges the ``backgrounds``,
    ``nested_features`` and ``nested_items`` namespaces via
    ``cache_namespaces``.
    """

    repository: BackgroundSkillsRepository

    cache_namespaces = BACKGROUND_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=BackgroundSkillsRepository(db),
            response_schema=BackgroundResponse,
        )

    async def resolve_skills(self, skill_ids: list[int] | None) -> list[Skill] | None:
        """
        Resolve ``skill_ids`` to ``Skill`` rows, or ``None`` when absent/empty.

        Raises ``RecordIdsInvalidError`` if any id doesn't correspond to an
        existing skill. Shared with ``create_background`` so it can seed the
        granted skills in the same transaction.
        """

        return await self._resolve_skills(skill_ids)

    async def set_skills_for_background(
        self, background: Background, skills: list[Skill], *, commit: bool = True
    ) -> None:
        """Attach ``skills`` to an existing ``background`` row (used by ``create_background``)."""

        await self.repository.set_skills(background, skills, commit=commit)
