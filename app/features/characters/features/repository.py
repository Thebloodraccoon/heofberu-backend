"""Repository for the feature grants recorded on a character (``character_features``)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import FeatureSourceType, GrantSource
from app.core.base.repository import BaseRepository
from app.models.character_engine_models import CharacterFeatureChoice
from app.models.character_feature_model import CharacterFeature
from app.models.feature_model import Feature

_WITH_CHOICES = selectinload(CharacterFeature.choices).selectinload(CharacterFeatureChoice.choice_option)


class CharacterFeatureRepository(BaseRepository[CharacterFeature]):
    """Repository for the features recorded on a character (``character_features``)."""

    def __init__(self, db: AsyncSession):
        """Create the feature-grant repository."""

        super().__init__(
            CharacterFeature,
            db,
            default_load_options=[selectinload(CharacterFeature.feature)],
        )

    async def get_character_features(self, character_id: int) -> list[CharacterFeature]:
        """
        Get every feature grant for a character, EXCLUDING feats.

        A feat is a ``character_features`` row whose ``feature.source_type
        == FEAT`` too (a feat IS a Feature), but it is surfaced through
        ``GET /characters/{id}/feats`` — excluding it here keeps the same
        grant from appearing twice in the character sheet.
        """

        result = await self.db.execute(
            select(CharacterFeature)
            .join(Feature, Feature.id == CharacterFeature.feature_id)
            .options(selectinload(CharacterFeature.feature), _WITH_CHOICES)
            .where(CharacterFeature.character_id == character_id, Feature.source_type != FeatureSourceType.FEAT)
        )
        return list(result.scalars().unique().all())

    async def get_character_feature_by_id(
        self, character_id: int, character_feature_id: int
    ) -> CharacterFeature | None:
        """Fetch a single feature grant by its own id, scoped to the character."""

        result = await self.db.execute(
            select(CharacterFeature)
            .options(selectinload(CharacterFeature.feature))
            .where(
                CharacterFeature.id == character_feature_id,
                CharacterFeature.character_id == character_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_character_feature_by_feature_id(self, character_id: int, feature_id: int) -> CharacterFeature | None:
        """Fetch a character's grant for a specific reference feature, if any (used for duplicate checks)."""

        result = await self.db.execute(
            select(CharacterFeature).where(
                CharacterFeature.character_id == character_id,
                CharacterFeature.feature_id == feature_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_character_feature(
        self,
        character_id: int,
        feature_id: int,
        notes: str,
        *,
        grant_source: GrantSource = GrantSource.GM,
        commit: bool = True,
    ) -> CharacterFeature:
        """
        Record a reference feature on a character, with per-character notes.

        ``grant_source`` defaults to ``GM`` (this is the manual-grant path —
        auto-synced grants are written by
        ``progression.feature_sync.sync_progression_features`` with
        ``AUTO``) so a subsequent sync never mistakes a GM's manual grant
        for a stale auto-grant and revokes it. ``commit=False`` flushes
        instead, for callers running inside their own ``_atomic()``.
        """

        grant = CharacterFeature(
            character_id=character_id,
            feature_id=feature_id,
            grant_source=grant_source,
            notes=notes,
        )

        self.db.add(grant)
        await self.commit_or_flush(commit=commit)

        result = await self.db.execute(
            select(CharacterFeature)
            .options(selectinload(CharacterFeature.feature))
            .where(CharacterFeature.id == grant.id)
        )
        return result.scalar_one()

    async def update_notes(self, grant: CharacterFeature, notes: str) -> CharacterFeature:
        """Replace the notes on an existing feature grant."""

        grant.notes = notes
        await self.commit_or_flush()

        return grant

    async def remove_character_feature(self, grant: CharacterFeature) -> bool:
        """Remove a feature grant from a character."""

        await self.db.delete(grant)
        await self.commit_or_flush()
        return True
