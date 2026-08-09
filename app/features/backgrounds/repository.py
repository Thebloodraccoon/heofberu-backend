"""Background repository: base CRUD plus granted-skill management."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base_repository import BaseRepository
from app.models import CharacterFeature, Feature
from app.models.background_model import Background
from app.models.skill_model import Skill


class BackgroundRepository(BaseRepository[Background]):
    """Background-specific repository built on :class:`BaseRepository`."""

    def __init__(self, db: AsyncSession):
        super().__init__(
            Background,
            db,
            default_load_options=[selectinload(Background.granted_skills), selectinload(Background.features)],
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    async def is_in_use(self, background_id: int) -> bool:
        """
        Check whether any of the background's features is currently granted
        to a character (``character_features``). Characters may keep being
        detached via ``characters.background_id`` ``ON DELETE SET NULL`` —
        only granting its features blocks deletion.
        """

        result = await self.db.execute(select(Feature.id).where(Feature.background_id == background_id))
        feature_ids = [row[0] for row in result.all()]
        if not feature_ids:
            return False

        result = await self.db.execute(select(CharacterFeature).where(CharacterFeature.feature_id.in_(feature_ids)))
        return result.scalar_one_or_none() is not None

    async def get_skills_by_ids(self, skill_ids: list[int]) -> list[Skill]:
        """Fetch the skills matching ``skill_ids`` (order not guaranteed)."""

        if not skill_ids:
            return []

        result = await self.db.execute(select(Skill).where(Skill.id.in_(skill_ids)))
        return list(result.scalars().unique().all())

    async def set_skills(self, background: Background, skills: list[Skill], *, commit: bool = True) -> Background:
        """
        Replace all granted skills for a background with the given list.

        ``commit`` lets callers that need atomicity across multiple writes
        (e.g. creating a background + its skills together) defer the
        commit and flush instead, without duplicating this method. See
        ``RaceRepository.set_skills`` for the same pattern.
        """

        background.granted_skills = skills

        if commit:
            await self.db.commit()
            await self.db.refresh(background)
        else:
            await self.db.flush()

        return background
