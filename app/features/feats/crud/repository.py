"""Feat repository: base CRUD plus ASI-choice management and in-use guard."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models.character_association_models import CharacterFeat
from app.models.feat_model import Feat, FeatAbilityScoreIncrease


class FeatRepository(BaseRepository[Feat]):
    """
    Feat-specific repository built on :class:`BaseRepository`.

    ``ability_score_increases`` is always part of ``FeatResponse``, so it's
    wired up via ``default_load_options``.
    """

    def __init__(self, db: AsyncSession):
        """Configure the repository with its model, eager loads, and delete guard."""

        super().__init__(
            Feat,
            db,
            default_load_options=[
                selectinload(Feat.ability_score_increases),
            ],
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    async def is_in_use(self, feat_id: int) -> bool:
        """Check whether the feat is currently granted to any character, which blocks deletion."""

        granted = await self.db.execute(select(CharacterFeat).where(CharacterFeat.feat_id == feat_id))
        return granted.scalar_one_or_none() is not None

    async def set_ability_score_increases(self, feat: Feat, increases: list[dict], *, commit: bool = True) -> Feat:
        """Replace all ASI choices for a feat with the given list."""

        await self.replace_child_rows(
            FeatAbilityScoreIncrease,
            feat,
            "feat_id",
            increases,
            commit=commit,
        )

        return feat
