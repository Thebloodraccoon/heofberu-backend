"""Class skill repository: available-skill lookup and replacement."""

from app.features.classes.crud.repository import ClassRepository
from app.features.shared.skills.mixins import SkillLookupMixin
from app.models import class_available_skills
from app.models.class_model import Class
from app.models.skill_model import Skill


class ClassSkillsRepository(SkillLookupMixin, ClassRepository):
    """Class repository extended with available-skill management."""

    async def set_available_skills(self, character_class: Class, skills: list[Skill], *, commit: bool = True) -> Class:
        """
        Replace all skills a class may choose proficiencies from.

        Written through the association table (delete + insert) instead of
        assigning the ORM relationship, which would trigger an unsupported
        lazy load on the async stack.
        """

        await self.replace_association(
            class_available_skills,
            character_class,
            "class_id",
            "skill_id",
            [skill.id for skill in (skills or [])],
            commit=commit,
        )

        return character_class
