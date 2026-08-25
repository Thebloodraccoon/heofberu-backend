"""Feature repository: base CRUD plus fixed ability-increase effect management."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models.feature_model import Feature, FeatureAbilityIncrease


class FeatureRepository(BaseRepository[Feature]):
    """
    Feature-specific repository built on :class:`BaseRepository`.

    ``ability_increases`` (the feature's fixed ability-score effects) are
    always loaded alongside the row via ``default_load_options`` — they are
    small child rows and several reads serialize them.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(
            Feature,
            db,
            default_load_options=[
                selectinload(Feature.ability_increases),
            ],
            search_fields=["name"],
        )

    async def set_ability_increases(self, feature: Feature, increases: list[dict], *, commit: bool = True) -> Feature:
        """
        Replace all fixed ability-score increases for a feature with the
        given list.

        ``commit`` lets callers that need atomicity across multiple writes
        defer the commit and flush instead, without duplicating this method.
        """

        await self.replace_child_rows(
            FeatureAbilityIncrease,
            feature,
            "feature_id",
            increases,
            commit=commit,
        )

        return feature
