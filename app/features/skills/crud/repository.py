"""Skill repository: base CRUD plus reference lookups and in-use guard."""

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ProficiencyType
from app.core.base.repository import BaseRepository
from app.features.shared.skills.mixins import SkillLookupMixin
from app.models import Skill, background_skills, class_available_skills, race_skills
from app.models.character.character_proficiency_model import CharacterProficiency
from app.models.features.feature_engine_models import FeatureSkillProficiencyEffect


class SkillRepository(SkillLookupMixin, BaseRepository[Skill]):
    """Skill-specific repository built on :class:`BaseRepository`."""

    def __init__(self, db: AsyncSession):
        """Initialise the skill repository with name uniqueness and the in-use guard."""

        super().__init__(
            Skill,
            db,
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    async def is_in_use(self, skill_id: int) -> bool:
        """Check whether the skill is referenced anywhere that blocks deletion."""

        query = select(
            or_(
                exists().where(race_skills.c.skill_id == skill_id),
                exists().where(class_available_skills.c.skill_id == skill_id),
                exists().where(background_skills.c.skill_id == skill_id),
                exists().where(
                    CharacterProficiency.proficiency_type == ProficiencyType.SKILL,
                    CharacterProficiency.skill_id == skill_id,
                ),
                exists().where(FeatureSkillProficiencyEffect.skill_id == skill_id),
            )
        )
        return bool(await self.db.scalar(query))

    async def delete(self, db_obj: Skill) -> bool:
        """
        Delete the skill unless something references it.

        Most references cascade (character proficiencies) or are plain
        association rows, so a link added between the guard and the DELETE
        would be dropped silently. Locking the skill row first makes a
        concurrent insert (which takes a key-share lock on it) wait.
        """

        await self.db.execute(select(Skill.id).where(Skill.id == db_obj.id).with_for_update())
        return await super().delete(db_obj)
