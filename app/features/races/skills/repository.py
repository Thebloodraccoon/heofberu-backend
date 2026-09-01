"""Race skill repository: granted-skill lookup and replacement."""

from app.features.races.crud.repository import RaceRepository
from app.features.shared.skills.mixins import SkillLookupMixin
from app.models.race_association_models import race_skills
from app.models.race_model import Race
from app.models.skill_model import Skill


class RaceSkillsRepository(SkillLookupMixin, RaceRepository):
    """Race repository extended with granted-skill management."""

    async def set_skills(self, race: Race, skills: list[Skill], *, commit: bool = True) -> Race:
        """Replace all granted skills for a race with the given list."""

        await self.replace_association(
            race_skills,
            race,
            "race_id",
            "skill_id",
            [skill.id for skill in (skills or [])],
            commit=commit,
        )

        return race
