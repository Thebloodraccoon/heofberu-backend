"""Class available-skill service: full replacement and id resolution."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.classes.cache import CLASS_CACHE_NAMESPACES
from app.features.classes.schemas import (
    AvailableSkillsUpdate,
    ClassCreate,
    ClassResponse,
    ClassUpdate,
)
from app.features.classes.skills.repository import ClassSkillsRepository
from app.features.shared.skills.mixins import SkillsManagerMixin
from app.models.class_model import Class
from app.models.skill_model import Skill


class ClassSkillService(
    SkillsManagerMixin,
    BaseService[Class, ClassCreate, ClassUpdate, ClassResponse, None],
):
    """

    Everything about the skills a class may choose proficiencies from.

    Full replacement comes from :class:`SkillsManagerMixin` (pinned to the
    repository's ``set_available_skills`` via ``_set_skills_method``); the
    generic CRUD machinery (``_get_or_404``/``_get_response``/
    ``_invalidate_cache``) comes from :class:`BaseService`. Any write
    purges the ``classes``, ``nested_features`` and ``nested_items``
    namespaces via ``cache_namespaces``.
    """

    repository: ClassSkillsRepository

    _set_skills_method = "set_available_skills"

    cache_namespaces = CLASS_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=ClassSkillsRepository(db),
            response_schema=ClassResponse,
        )

    async def set_available_skills(self, class_id: int, data: AvailableSkillsUpdate) -> ClassResponse:
        """Fully replace the skills a class may choose proficiencies from."""

        return await self.set_skills(class_id, data)

    async def resolve_skills(self, skill_ids: list[int] | None) -> list[Skill] | None:
        """

        Resolve ``skill_ids`` to ``Skill`` rows, or ``None`` when absent/empty.

        Raises ``RecordIdsInvalidError`` if any id doesn't correspond to an
        existing skill. Shared with ``create_class`` so it can seed the
        available skills in the same transaction.
        """

        return await self._resolve_skills(skill_ids)

    async def set_skills_for_class(self, character_class: Class, skills: list[Skill], *, commit: bool = True) -> None:
        """Attach ``skills`` to an existing ``class`` row (used by ``create_class``)."""

        await self.repository.set_available_skills(character_class, skills, commit=commit)
