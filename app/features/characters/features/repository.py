"""Repository for the feature grants recorded on a character (``character_features``)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models.character_feature_model import CharacterFeature


class CharacterFeatureRepository(BaseRepository[CharacterFeature]):
    """
    Repository for the features recorded on a character
    (``character_features``).

    Split out of ``CharacterRepository`` — feature grants are their own
    association table, unrelated to the ``Character`` row's own columns.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(
            CharacterFeature,
            db,
            default_load_options=[selectinload(CharacterFeature.feature)],
        )

    async def get_character_features(self, character_id: int) -> list[CharacterFeature]:
        """Get every feature grant for a character."""

        result = await self.db.execute(
            select(CharacterFeature)
            .options(selectinload(CharacterFeature.feature))
            .where(CharacterFeature.character_id == character_id)
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

    async def add_character_feature(self, character_id: int, feature_id: int, notes: str) -> CharacterFeature:
        """Record a reference feature on a character, with per-character notes."""

        grant = CharacterFeature(
            character_id=character_id,
            feature_id=feature_id,
            notes=notes,
        )

        self.db.add(grant)
        await self.db.commit()

        result = await self.db.execute(
            select(CharacterFeature)
            .options(selectinload(CharacterFeature.feature))
            .where(CharacterFeature.id == grant.id)
        )
        return result.scalar_one()

    async def update_notes(self, grant: CharacterFeature, notes: str) -> CharacterFeature:
        """Replace the notes on an existing feature grant."""

        grant.notes = notes
        await self.db.commit()

        return grant

    async def remove_character_feature(self, grant: CharacterFeature) -> bool:
        """Remove a feature grant from a character."""

        await self.db.delete(grant)
        await self.db.commit()
        return True