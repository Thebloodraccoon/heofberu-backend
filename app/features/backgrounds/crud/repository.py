"""Background repository: base CRUD plus the delete-in-use guard."""

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.features.features.crud.repository import feature_summary_loads
from app.models import Background, CharacterFeature, Feature, SourceItem
from app.models.items.item_source_choice_model import SourceItemChoiceGroup, SourceItemChoiceOption


class BackgroundRepository(BaseRepository[Background]):
    """Background-specific repository built on :class:`BaseRepository`."""

    def __init__(self, db: AsyncSession):
        """Configure the repository with its model, eager loads, and delete guard."""

        super().__init__(
            Background,
            db,
            default_load_options=[
                selectinload(Background.granted_skills),
                selectinload(Background.starting_items).selectinload(SourceItem.item),
                selectinload(Background.starting_choice_groups)
                .selectinload(SourceItemChoiceGroup.options)
                .selectinload(SourceItemChoiceOption.item),
                selectinload(Background.suggestions),
                selectinload(Background.tags),
                *feature_summary_loads(selectinload(Background.features)),
            ],
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    async def get_bare(self, background_id: int) -> Background | None:
        """Fetch the background row alone, without the eager-loaded aggregate (enough for deletes)."""

        return await self.db.get(Background, background_id)

    async def is_in_use(self, background_id: int) -> bool:
        """Whether any feature of the background is granted to a character, which blocks deletion."""

        granted = exists().where(
            CharacterFeature.feature_id == Feature.id,
            Feature.background_id == background_id,
        )
        return bool(await self.db.scalar(select(granted)))

    async def delete(self, db_obj: Background) -> bool:
        """
        Delete the background unless one of its features is granted to a character.

        ``character_features.feature_id`` cascades, so a grant slipping in
        between the guard and the DELETE would be wiped silently. Locking the
        background's feature rows first makes a concurrent grant (which takes
        a key-share lock on the feature) wait for this transaction.
        """

        await self.db.execute(select(Feature.id).where(Feature.background_id == db_obj.id).with_for_update())
        return await super().delete(db_obj)
