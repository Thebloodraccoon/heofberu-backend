"""Background skills repository: granted-skill lookup and full replacement."""

from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.shared.skills.mixins import SkillLookupMixin
from app.models.background_association_models import background_skills
from app.models.background_model import Background
from app.models.skill_model import Skill


class BackgroundSkillsRepository(SkillLookupMixin, BackgroundRepository):
    """
    Granted-skill persistence for backgrounds.

    Extends :class:`BackgroundRepository` (so fetches carry the eager loads
    ``BackgroundResponse`` needs) and adds the shared skill-id lookup from
    :class:`SkillLookupMixin`.
    """

    async def set_skills(self, background: Background, skills: list[Skill], *, commit: bool = True) -> Background:
        """
        Replace all granted skills for a background with the given list.

        Written through the association table (delete + insert) instead of
        assigning the ORM ``granted_skills`` relationship: assigning an
        unloaded many-to-many collection would trigger a lazy load, which
        is not supported on the async stack. See ``RaceRepository.set_skills``
        for the same pattern.

        ``commit`` lets callers that need atomicity across multiple writes
        (e.g. creating a background + its skills together) defer the
        commit and flush instead, without duplicating this method.
        """

        await self.replace_association(
            background_skills,
            background,
            "background_id",
            "skill_id",
            [skill.id for skill in skills],
            commit=commit,
        )

        return background
