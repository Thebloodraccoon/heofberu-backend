"""Repository for the feat grants recorded on a character (``character_feats``)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import CharacterFeatSource
from app.core.base.repository import BaseRepository
from app.models.character_association_models import CharacterFeat


class CharacterFeatRepository(BaseRepository[CharacterFeat]):
    """
    Repository for a character's granted feats (``character_feats``).

    Split out of ``CharacterRepository`` — feat grants are their own
    association table, unrelated to the ``Character`` row's own columns.

    Every read eager-loads ``CharacterFeat.feat`` and
    ``CharacterFeat.ability_score_increase``: the grant rows are serialized
    with an embedded feat brief and the resolved ability score increase, and
    lazy-loading either relationship in the async session would fail.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(CharacterFeat, db)

    async def get_character_feats(self, character_id: int) -> list[CharacterFeat]:
        """Get every feat grant for a character."""

        result = await self.db.execute(
            select(CharacterFeat)
            .options(
                selectinload(CharacterFeat.feat),
                selectinload(CharacterFeat.ability_score_increase),
            )
            .where(CharacterFeat.character_id == character_id)
        )
        return list(result.scalars().unique().all())

    async def get_character_feat_by_id(self, character_id: int, character_feat_id: int) -> CharacterFeat | None:
        """Fetch a single feat grant by its own id, scoped to the character."""

        result = await self.db.execute(
            select(CharacterFeat)
            .options(
                selectinload(CharacterFeat.feat),
                selectinload(CharacterFeat.ability_score_increase),
            )
            .where(
                CharacterFeat.id == character_feat_id,
                CharacterFeat.character_id == character_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_character_feat_by_feat_id(self, character_id: int, feat_id: int) -> CharacterFeat | None:
        """Fetch a character's grant for a specific feat, if any (used for duplicate checks)."""

        result = await self.db.execute(
            select(CharacterFeat).where(
                CharacterFeat.character_id == character_id,
                CharacterFeat.feat_id == feat_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_character_feat(
        self,
        character_id: int,
        feat_id: int,
        ability_score_increase_id: int | None,
        *,
        source_type: CharacterFeatSource | str = CharacterFeatSource.GM,
        commit: bool = True,
    ) -> CharacterFeat:
        """
        Grant a feat to a character, with an optional ASI choice.

        ``source_type`` records where the grant came from (default ``GM`` —
        the manual feats endpoint; the level-up endpoint passes ``ASI``).
        ``commit=False`` defers the commit so callers that wrap the grant in
        a transaction (``CharacterProgressionService._atomic``) can commit
        it together with the rest of the level-up.
        """

        grant = CharacterFeat(
            character_id=character_id,
            feat_id=feat_id,
            ability_score_increase_id=ability_score_increase_id,
            source_type=source_type,
        )

        self.db.add(grant)
        if commit:
            await self.db.commit()
        else:
            await self.db.flush()

        return await self._reload_with_feat(grant.id)

    async def set_character_feat_ability_score_increase(
        self, grant: CharacterFeat, ability_score_increase_id: int | None
    ) -> CharacterFeat:
        """Set (or clear, if ``None``) the ASI choice on an existing feat grant."""

        grant.ability_score_increase_id = ability_score_increase_id
        await self.db.commit()

        return await self._reload_with_feat(grant.id)

    async def _reload_with_feat(self, grant_id: int) -> CharacterFeat:
        """Re-fetch a grant with its feat and ASI choice eager-loaded (for safe serialization)."""

        result = await self.db.execute(
            select(CharacterFeat)
            .options(
                selectinload(CharacterFeat.feat),
                selectinload(CharacterFeat.ability_score_increase),
            )
            .where(CharacterFeat.id == grant_id)
        )
        return result.scalar_one()

    async def remove_character_feat(self, grant: CharacterFeat) -> bool:
        """Revoke a feat grant."""

        await self.db.delete(grant)
        await self.db.commit()
        return True