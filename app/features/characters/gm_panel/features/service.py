"""GM feature-grant service: record/remove reference features on a character."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType, GrantSource
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.cache import invalidate_character_cache
from app.features.characters.features.repository import CharacterFeatureRepository
from app.features.characters.features.schemas import CharacterFeatureBriefResponse, CharacterFeatureResponse
from app.features.characters.gm_panel.exceptions import (
    CharacterFeatureAlreadyKnownException,
    CharacterFeatureNotFoundException,
    FeatureIsAFeatException,
)
from app.features.characters.gm_panel.features.schemas import CharacterFeatureAdd
from app.features.characters.grants.schemas import GrantEffectsResponse
from app.features.characters.grants.service import FeatureGrantService
from app.features.features.crud.repository import FeatureRepository
from app.features.features.exceptions import FeatureNotFoundException
from app.features.users.schemas import UserResponse
from app.models.character.character_feature_model import CharacterFeature
from app.models.character.character_model import Character


class GmPanelFeatureService(CharacterSubDomainService):
    """
    Grant management for reference features (``character_features``);
    adds/removals refresh the ability-score cache. The grant's other
    effects (skills, saves, armor/weapons, spells) are computed on read.
    """

    def __init__(self, db: AsyncSession):
        """Wire up the feature/repo repositories and ability-score service."""

        super().__init__(db)
        self.feature_grant_repository = CharacterFeatureRepository(db)
        self.feature_repository = FeatureRepository(db)
        self.stats_service = CharacterStatsService(db)
        self.grant_service = FeatureGrantService(db)

    async def add_feature(
        self, character_id: int, data: CharacterFeatureAdd, current_user: UserResponse
    ) -> CharacterFeatureResponse:
        """Record a reference feature on a character."""

        character = await self.get_character_for_user(character_id, current_user)

        feature = await self.feature_repository.get_by_id(data.feature_id)
        if feature is None:
            raise FeatureNotFoundException(feature_id=data.feature_id)

        if feature.source_type == FeatureSourceType.FEAT:
            raise FeatureIsAFeatException(feature_id=data.feature_id)

        existing = await self.feature_grant_repository.get_character_feature_by_feature_id(
            character_id, data.feature_id
        )
        if existing:
            raise CharacterFeatureAlreadyKnownException(character_id=character_id, feature_id=data.feature_id)

        async with self._atomic():
            grant = await self.feature_grant_repository.add_character_feature(
                character_id, data.feature_id, grant_source=GrantSource.GM, commit=False
            )
            await self.grant_service.resolve_grant_choices(character, grant, data.choices, enforce=False)
            await self._refresh_stats(character)

        return self._to_response(grant)

    async def remove_feature(self, character_id: int, character_feature_id: int, current_user: UserResponse) -> bool:
        """Remove a feature grant from a character."""

        character = await self.get_character_for_user(character_id, current_user)

        grant = await self._get_feature_grant_or_404(character_id, character_feature_id)

        async with self._atomic():
            result = await self.feature_grant_repository.remove_character_feature(grant, commit=False)
            await self._refresh_stats(character)

        return result

    async def _refresh_stats(self, character: Character) -> None:
        """Recompute the ability-score cache in the caller's transaction; purge the payload after its commit."""

        await self.stats_service.refresh(character, commit=False)
        await invalidate_character_cache(character.id, db=self.repository.db)

    @staticmethod
    def _to_response(grant: CharacterFeature) -> CharacterFeatureResponse:
        """
        Build a ``CharacterFeatureResponse`` for a write response without
        touching ``grant.choices`` (not eager-loaded here — a lazy load
        would raise ``MissingGreenlet`` under the async session). GM
        add/update responses carry empty ``effects``/``choices``; the full
        materialized picture is served by the player-facing listing.
        """

        return CharacterFeatureResponse(
            id=grant.id,
            character_id=grant.character_id,
            feature_id=grant.feature_id,
            grant_source=grant.grant_source,
            feature=CharacterFeatureBriefResponse.model_validate(grant.feature),
            effects=GrantEffectsResponse(),
            choices=[],
        )

    async def _get_feature_grant_or_404(self, character_id: int, character_feature_id: int) -> CharacterFeature:
        """Fetch a feature grant scoped to the character, or raise ``CharacterFeatureNotFoundException``."""

        grant = await self.feature_grant_repository.get_character_feature_by_id(character_id, character_feature_id)
        if not grant:
            raise CharacterFeatureNotFoundException(
                character_id=character_id, character_feature_id=character_feature_id
            )

        return grant
