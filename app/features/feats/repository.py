"""Feat repository: base CRUD plus ASI-choice management and in-use guard."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base_repository import BaseRepository
from app.models import CharacterFeature, Feature
from app.models.character_association_models import CharacterFeat
from app.models.feat_model import Feat, FeatAbilityScoreIncrease


class FeatRepository(BaseRepository[Feat]):
    """
    Feat-specific repository built on :class:`BaseRepository`.

    ``ability_score_increases`` is always part of ``FeatResponse``, so it's
    wired up as ``default_load_options`` rather than re-implemented via a
    hand-rolled ``get_all`` override — same reasoning as ``RaceRepository``.
    The feat's ``features`` are no longer embedded in the response; they're
    read through the dedicated ``nested_features`` cache.
    """

    def __init__(self, db: AsyncSession):
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
        """
        Check whether the feat is currently granted to any character
        (``character_feats.feat_id``) or any of its features is currently
        granted to a character (``character_features``), either of which
        blocks deletion.

        Note: a plain ``Feature`` row referencing the feat does NOT block
        deletion anymore — deleting the feat cascades to its features, which
        is exactly how a feat's own benefits are meant to be removed.
        """

        granted = await self.db.execute(select(CharacterFeat).where(CharacterFeat.feat_id == feat_id))
        if granted.scalar_one_or_none() is not None:
            return True

        result = await self.db.execute(select(Feature.id).where(Feature.feat_id == feat_id))
        feature_ids = [row[0] for row in result.all()]
        if not feature_ids:
            return False

        result = await self.db.execute(select(CharacterFeature).where(CharacterFeature.feature_id.in_(feature_ids)))
        return result.scalar_one_or_none() is not None

    async def set_ability_score_increases(self, feat: Feat, increases: list[dict], *, commit: bool = True) -> Feat:
        """
        Replace all ASI choices for a feat with the given list.

        ``commit`` lets callers that need atomicity across multiple writes
        (e.g. creating a feat + its ASI choices together) defer the commit
        and flush instead, without duplicating this method.
        """

        await self.replace_child_rows(
            FeatAbilityScoreIncrease,
            feat,
            "feat_id",
            increases,
            commit=commit,
        )

        return feat
