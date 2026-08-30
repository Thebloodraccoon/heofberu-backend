"""Background repository: base CRUD plus the delete-in-use guard."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models import Background, CharacterFeature, Feature, SourceItem
from app.models.source_item_choice_model import SourceItemChoiceGroup, SourceItemChoiceOption


class BackgroundRepository(BaseRepository[Background]):
    """Background-specific repository built on :class:`BaseRepository`."""

    def __init__(self, db: AsyncSession):
        super().__init__(
            Background,
            db,
            default_load_options=[
                selectinload(Background.granted_skills),
                selectinload(Background.starting_items).selectinload(SourceItem.item),
                selectinload(Background.starting_choice_groups)
                .selectinload(SourceItemChoiceGroup.options)
                .selectinload(SourceItemChoiceOption.item),
            ],
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
