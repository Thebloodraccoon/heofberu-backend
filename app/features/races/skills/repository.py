"""Race skill repository: granted-skill lookup and replacement."""

from app.features.races.crud.repository import RaceRepository
from app.features.shared.skills.mixins import SkillLookupMixin
from app.models.races.race_association_models import race_skills
from app.models.races.race_model import Race
from app.models.skill_model import Skill


class RaceSkillsRepository(SkillLookupMixin, RaceRepository):
    """Race repository extended with granted-skill management."""

    async def set_skills(self, race_id: int, skills: list[Skill], *, commit: bool = True) -> None:
        """Replace all granted skills for a race with the given list."""

        await self.replace_association(
            race_skills,
            Race(id=race_id),
            "race_id",
            "skill_id",
            [skill.id for skill in (skills or [])],
            commit=commit,
        )
