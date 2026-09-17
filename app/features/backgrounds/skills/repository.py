"""Background skills repository: granted-skill lookup and full replacement."""

from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.shared.skills.mixins import SkillLookupMixin
from app.models import Background, Skill, background_skills


class BackgroundSkillsRepository(SkillLookupMixin, BackgroundRepository):
    """
    Granted-skill persistence for backgrounds.

    Extends :class:`BackgroundRepository` and adds the shared skill-id lookup
    from :class:`SkillLookupMixin`.
    """

    async def set_skills(self, background_id: int, skills: list[Skill], *, commit: bool = True) -> None:
        """
        Replace all granted skills for a background.

        Written through the association table (delete + insert) rather than
        the ORM relationship to avoid an async lazy load; ``commit`` lets
        atomic multi-write callers defer the commit.
        """

        await self.replace_association(
            background_skills,
            Background(id=background_id),
            "background_id",
            "skill_id",
            [skill.id for skill in (skills or [])],
            commit=commit,
        )
