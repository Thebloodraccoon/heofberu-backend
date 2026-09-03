"""GM feat-grant service: grant/update/revoke reference feats on a character."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ASILevelChoice
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.cache import invalidate_character_cache
from app.features.characters.feats.exceptions import CharacterFeatAlreadyKnownException
from app.features.characters.feats.repository import CharacterFeatRepository
from app.features.characters.feats.validation import (
    check_feat_prerequisite,
    validate_ability_score_increase,
    validate_asi_choice_required,
)
from app.features.characters.gm_panel.exceptions import CharacterFeatNotFoundException
from app.features.characters.gm_panel.feats.schemas import CharacterFeatAdd, CharacterFeatUpdate
from app.features.characters.progression.feature_sync import sync_progression_features
from app.features.characters.progression.repository import CharacterASIChoiceRepository
from app.features.characters.schemas import CharacterFeatResponse
from app.features.feats.crud.repository import FeatRepository
from app.features.feats.exceptions import FeatNotFoundException
from app.features.users.schemas import UserResponse
from app.models.character_association_models import CharacterFeat
from app.models.feat_model import Feat


class GmPanelFeatService(CharacterSubDomainService):
    """
    Grant management for reference feats (``character_feats``); each grant
    writes an audit row into ``character_asi_choices`` and refreshes the
    ability-score cache plus auto-granted features.
    """

    def __init__(self, db: AsyncSession):
        """Wire up the feat/ASI/reference repositories and the ability-score service."""

        super().__init__(db)
        self.feat_grant_repository = CharacterFeatRepository(db)
        self.stats_service = CharacterStatsService(db)
        self.feat_repository = FeatRepository(db)
        self.asi_repository = CharacterASIChoiceRepository(db)

    async def add_feat(
        self, character_id: int, data: CharacterFeatAdd, current_user: UserResponse
    ) -> CharacterFeatResponse:
        """
        Grant a feat outside any level-up flow, committing its
        ``character_asi_choices`` audit row and feature re-sync atomically.
        """

        character = await self.get_character_for_user(character_id, current_user)

        feat = await self.feat_repository.get_by_id(data.feat_id)
        if not feat:
            raise FeatNotFoundException(feat_id=data.feat_id)

        existing = await self.feat_grant_repository.get_character_feat_by_feat_id(character_id, data.feat_id)
        if existing:
            raise CharacterFeatAlreadyKnownException(character_id=character_id, feat_id=data.feat_id)

        self._validate_asi_choice(feat, data.ability_score_increase_id)
        await check_feat_prerequisite(character, feat, self.stats_service)

        async with self._atomic():
            grant = await self.feat_grant_repository.add_character_feat(
                character_id, data.feat_id, data.ability_score_increase_id, commit=False
            )
            await self.asi_repository.add(
                character.id,
                None,
                ASILevelChoice.FEAT,
                feat_id=data.feat_id,
                ability_score_increase_id=data.ability_score_increase_id,
                commit=False,
            )
            await sync_progression_features(self.repository.db, character)

        await self.stats_service.refresh(character)
        await invalidate_character_cache(character_id)

        return CharacterFeatResponse.model_validate(grant)

    async def update_feat(
        self,
        character_id: int,
        character_feat_id: int,
        data: CharacterFeatUpdate,
        current_user: UserResponse,
    ) -> CharacterFeatResponse:
        """Change the ASI choice for an already-granted feat."""

        character = await self.get_character_for_user(character_id, current_user)

        grant = await self._get_feat_grant_or_404(character_id, character_feat_id)

        feat = await self.feat_repository.get_by_id(grant.feat_id)
        self._validate_asi_choice(feat, data.ability_score_increase_id)

        updated_grant = await self.feat_grant_repository.set_character_feat_ability_score_increase(
            grant, data.ability_score_increase_id
        )

        await self.stats_service.refresh(character)
        await invalidate_character_cache(character_id)
        return CharacterFeatResponse.model_validate(updated_grant)

    async def remove_feat(self, character_id: int, character_feat_id: int, current_user: UserResponse) -> bool:
        """Revoke a feat from a character."""

        character = await self.get_character_for_user(character_id, current_user)

        grant = await self._get_feat_grant_or_404(character_id, character_feat_id)
        result = await self.feat_grant_repository.remove_character_feat(grant)
        await sync_progression_features(self.repository.db, character)
        await self.repository.db.commit()

        await self.stats_service.refresh(character)
        await invalidate_character_cache(character_id)

        return result

    @staticmethod
    def _validate_asi_choice(
            feat: Feat, ability_score_increase_id: int | None
    ) -> None:
        """Validate the ASI choice carried by a grant write (required, belongs to the feat, within cap)."""

        validate_asi_choice_required(feat, ability_score_increase_id)
        if ability_score_increase_id is not None:
            validate_ability_score_increase(feat, ability_score_increase_id)

    async def _get_feat_grant_or_404(self, character_id: int, character_feat_id: int) -> CharacterFeat:
        """Fetch a feat grant scoped to the character, or raise ``CharacterFeatNotFoundException``."""

        grant = await self.feat_grant_repository.get_character_feat_by_id(character_id, character_feat_id)
        if not grant:
            raise CharacterFeatNotFoundException(character_id=character_id, character_feat_id=character_feat_id)

        return grant
