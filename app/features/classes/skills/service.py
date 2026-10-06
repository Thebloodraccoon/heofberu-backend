"""Class available-skill service: full replacement."""

from app.features.classes.service_base import ClassScopedService
from app.features.classes.skills.schemas import AvailableSkillsUpdate
from app.features.shared.skills.mixins import SkillsManagerMixin


class ClassSkillService(SkillsManagerMixin, ClassScopedService):
    """
    The skills a class may choose proficiencies from.

    Full replacement comes from :class:`SkillsManagerMixin`.
    """

    _set_skills_method = "set_available_skills"

    async def set_available_skills(self, class_id: int, data: AvailableSkillsUpdate):
        """Fully replace the skills a class may choose proficiencies from."""

        return await self.set_skills(class_id, data)
