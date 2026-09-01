"""Shared skills mixins for lookup and full-replace operations."""

from typing import Any

from app.models.skill_model import Skill


class SkillLookupMixin:
    """Resolve skill IDs to Skill rows via the generic id-IN lookup."""

    async def get_skills_by_ids(self, skill_ids: list[int]) -> list[Skill]:
        """Fetch the skills matching ``skill_ids`` (order not guaranteed)."""

        return await self.get_many_by_ids(Skill, skill_ids)


class SkillsManagerMixin:
    """Fully replace the skills attached to a source record."""

    _set_skills_method: str = "set_skills"

    async def set_skills(self, source_id: int, data: Any) -> Any:
        """Fully replace the skills granted/available for ``source_id``."""

        record = await self._get_or_404(source_id)
        skills = await self._resolve_skills(data.skill_ids)

        await getattr(self.repository, self._set_skills_method)(record, skills)
        await self._invalidate_cache()

        return await self._get_response(source_id)

    async def _resolve_skills(self, skill_ids: list[int] | None) -> list[Skill] | None:
        """Resolve ``skill_ids`` to ``Skill`` rows, or ``None`` when absent/empty."""

        if not skill_ids:
            return None

        return await self.resolve_ids(self.repository.get_skills_by_ids, skill_ids, "Skills")
