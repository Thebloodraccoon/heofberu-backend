"""Skill repository: base CRUD plus reference lookups and in-use guard."""

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.repository import BaseRepository
from app.features.shared.skills.mixins import SkillLookupMixin
from app.models import CharacterSkillProficiency, Skill, background_skills, class_available_skills, race_skills


class SkillRepository(SkillLookupMixin, BaseRepository[Skill]):
    """Skill-specific repository built on :class:`BaseRepository`."""

    def __init__(self, db: AsyncSession):
        """Initialise the skill repository with name/key uniqueness."""

        super().__init__(
            Skill,
            db,
            search_fields=["name", "key"],
            unique_fields=["name", "key"],
            check_in_use_on_delete=True,
        )

    async def is_in_use(self, skill_id: int) -> bool:
        """Check whether the skill is referenced anywhere that blocks deletion."""

        query = select(
            or_(
                exists().where(race_skills.c.skill_id == skill_id),
                exists().where(class_available_skills.c.skill_id == skill_id),
                exists().where(background_skills.c.skill_id == skill_id),
                exists().where(CharacterSkillProficiency.skill_id == skill_id),
            )
        )
        result = await self.db.execute(query)
        return result.scalar()
