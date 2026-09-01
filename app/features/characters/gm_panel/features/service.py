"""GM feature-grant service: record/update/remove reference features on a character."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.cache import invalidate_character_cache
from app.features.characters.features.repository import CharacterFeatureRepository
from app.features.characters.gm_panel.exceptions import (
    CharacterFeatureAlreadyKnownException,
    CharacterFeatureNotFoundException,
)
from app.features.characters.gm_panel.features.schemas import CharacterFeatureAdd, CharacterFeatureUpdate
from app.features.characters.schemas import CharacterFeatureResponse
from app.features.features.crud.repository import FeatureRepository
from app.features.features.exceptions import FeatureNotFoundException
from app.features.users.schemas import UserResponse
from app.models.character_feature_model import CharacterFeature


class GmPanelFeatureService(CharacterSubDomainService):
    """
    Grant management for reference features (``character_features``);
    adds/removals refresh the ability-score cache (grants can carry fixed
    ability-score effects), notes updates don't.
    """

    def __init__(self, db: AsyncSession):
        """Wire up the feature/repo repositories and ability-score service."""

        super().__init__(db)
        self.feature_grant_repository = CharacterFeatureRepository(db)
        self.feature_repository = FeatureRepository(db)
        self.stats_service = CharacterStatsService(db)

    async def add_feature(
        self, character_id: int, data: CharacterFeatureAdd, current_user: UserResponse
    ) -> CharacterFeatureResponse:
        """Record a reference feature on a character, with optional notes."""

        character = await self.get_character_for_user(character_id, current_user)

        if not await self.feature_repository.exists_by_id(data.feature_id):
            raise FeatureNotFoundException(feature_id=data.feature_id)

        existing = await self.feature_grant_repository.get_character_feature_by_feature_id(
            character_id, data.feature_id
        )
        if existing:
            raise CharacterFeatureAlreadyKnownException(character_id=character_id, feature_id=data.feature_id)

        grant = await self.feature_grant_repository.add_character_feature(character_id, data.feature_id, data.notes)

        await self.stats_service.refresh(character)
        await invalidate_character_cache(character_id)
        return CharacterFeatureResponse.model_validate(grant)

    async def update_feature(
        self,
        character_id: int,
        character_feature_id: int,
        data: CharacterFeatureUpdate,
        current_user: UserResponse,
    ) -> CharacterFeatureResponse:
        """Replace the notes on an already-recorded feature."""

        await self.get_character_for_user(character_id, current_user)

        grant = await self._get_feature_grant_or_404(character_id, character_feature_id)
        updated_grant = await self.feature_grant_repository.update_notes(grant, data.notes or "")
        return CharacterFeatureResponse.model_validate(updated_grant)

    async def remove_feature(self, character_id: int, character_feature_id: int, current_user: UserResponse) -> bool:
        """Remove a feature grant from a character."""

        character = await self.get_character_for_user(character_id, current_user)

        grant = await self._get_feature_grant_or_404(character_id, character_feature_id)
        result = await self.feature_grant_repository.remove_character_feature(grant)

        await self.stats_service.refresh(character)
        await invalidate_character_cache(character_id)
        return result

    async def _get_feature_grant_or_404(self, character_id: int, character_feature_id: int) -> CharacterFeature:
        """Fetch a feature grant scoped to the character, or raise ``CharacterFeatureNotFoundException``."""

        grant = await self.feature_grant_repository.get_character_feature_by_id(character_id, character_feature_id)
        if not grant:
            raise CharacterFeatureNotFoundException(
                character_id=character_id, character_feature_id=character_feature_id
            )

        return grant
