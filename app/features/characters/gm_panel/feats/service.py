"""GM feat-grant service: grant/update/revoke reference feats on a character."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ASILevelChoice, GrantSource
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.feats.exceptions import CharacterFeatAlreadyKnownException
from app.features.characters.feats.repository import CharacterFeatRepository, to_character_feat_response
from app.features.characters.feats.schemas import CharacterFeatResponse
from app.features.characters.feats.validation import (
    check_feat_prerequisite,
    validate_ability_score_increase,
    validate_asi_choice_required,
)
from app.features.characters.gm_panel.exceptions import CharacterFeatNotFoundException
from app.features.characters.gm_panel.feats.schemas import CharacterFeatAdd, CharacterFeatUpdate
from app.features.characters.grants.service import FeatureGrantService
from app.features.characters.locking import lock_character
from app.features.characters.progression.feature_sync import sync_progression_features
from app.features.characters.progression.repository import CharacterASIChoiceRepository
from app.features.feats.crud.repository import FeatRepository
from app.features.feats.exceptions import FeatNotFoundException
from app.features.users.schemas import UserResponse
from app.models.character.character_feature_model import CharacterFeature
from app.models.character.character_model import Character
from app.models.features.feature_model import Feature


class GmPanelFeatService(CharacterSubDomainService):
    """
    Grant management for feats (``character_features`` rows whose
    ``feature.source_type == FEAT`` — a feat IS a Feature); each grant writes
    an audit row into ``character_asi_choices`` and refreshes the
    ability-score cache plus auto-granted features.
    """

    def __init__(self, db: AsyncSession):
        """Wire up the feat/ASI/reference repositories and the ability-score service."""

        super().__init__(db)
        self.feat_grant_repository = CharacterFeatRepository(db)
        self.stats_service = CharacterStatsService(db)
        self.feat_repository = FeatRepository(db)
        self.asi_repository = CharacterASIChoiceRepository(db)
        self.grant_service = FeatureGrantService(db)

    async def add_feat(
        self, character_id: int, data: CharacterFeatAdd, current_user: UserResponse
    ) -> CharacterFeatResponse:
        """
        Grant a feat outside any level-up flow, writing its
        ``character_asi_choices`` audit row and feature re-sync atomically.

        ``ability_score_increase_id`` is optional even for a feat offering
        ASI options — a GM can land the grant first and leave the ASI choice
        group pending, to be answered later like any other choice group.
        """

        character = await self.get_character_for_user(character_id, current_user)

        feat = await self.feat_repository.get_by_id(data.feat_id)
        if not feat:
            raise FeatNotFoundException(feat_id=data.feat_id)

        # Unlike ``update_feat``, a GM grant doesn't have to pick the ASI
        # choice up front: an omitted one just leaves the feat's ASI choice
        # group pending (see ``resolve_grant_choices(enforce=False)`` below),
        # answerable later like any other choice group. A *given* id still
        # has to belong to this feat.
        validate_ability_score_increase(feat, data.ability_score_increase_id)

        async with self._atomic():
            await lock_character(self.repository.db, character_id)
            existing = await self.feat_grant_repository.get_character_feat_by_feat_id(character_id, data.feat_id)
            if existing:
                raise CharacterFeatAlreadyKnownException(character_id=character_id, feat_id=data.feat_id)

            await check_feat_prerequisite(character, feat, self.stats_service)
            grant = await self.feat_grant_repository.add_character_feat(
                character, data.feat_id, data.ability_score_increase_id, source_type=GrantSource.GM
            )
            await self.asi_repository.add(
                character.id,
                None,
                ASILevelChoice.FEAT,
                feat_id=data.feat_id,
                ability_score_increase_id=data.ability_score_increase_id,
            )
            await sync_progression_features(self.repository.db, character)
            await self.grant_service.resolve_grant_choices(character, grant, data.choices, enforce=False)
            await self._refresh_stats(character)

        return to_character_feat_response(grant)

    async def update_feat(
        self,
        character_id: int,
        character_feat_id: int,
        data: CharacterFeatUpdate,
        current_user: UserResponse,
    ) -> CharacterFeatResponse:
        """Change the ASI choice for an already-granted feat."""

        character = await self.get_character_for_user(character_id, current_user)

        async with self._atomic():
            await lock_character(self.repository.db, character_id)
            grant = await self._get_feat_grant_or_404(character_id, character_feat_id)

            feat = await self.feat_repository.get_by_id(grant.feature_id)
            if feat is None:  # the grant's FK cascades, so only a concurrent delete gets here
                raise FeatNotFoundException(feat_id=grant.feature_id)
            self._validate_asi_choice(feat, data.ability_score_increase_id)

            updated_grant = await self.feat_grant_repository.set_character_feat_ability_score_increase(
                character, grant, data.ability_score_increase_id
            )
            await self._refresh_stats(character)

        return to_character_feat_response(updated_grant)

    async def remove_feat(self, character_id: int, character_feat_id: int, current_user: UserResponse) -> bool:
        """Revoke a feat from a character."""

        character = await self.get_character_for_user(character_id, current_user)

        async with self._atomic():
            await lock_character(self.repository.db, character_id)
            grant = await self._get_feat_grant_or_404(character_id, character_feat_id)
            result = await self.feat_grant_repository.remove_character_feat(grant)
            await sync_progression_features(self.repository.db, character)
            await self._refresh_stats(character)

        return result

    async def _refresh_stats(self, character: Character) -> None:
        """Recompute the ability-score cache in the caller's transaction; purge the payload after its commit."""

        await self.stats_service.refresh(character)
        await self._invalidate_character(character.id)

    @staticmethod
    def _validate_asi_choice(feat: Feature, ability_score_increase_id: int | None) -> None:
        """Validate the ASI choice carried by a grant write (required, belongs to the feat, within cap)."""

        validate_asi_choice_required(feat, ability_score_increase_id)
        if ability_score_increase_id is not None:
            validate_ability_score_increase(feat, ability_score_increase_id)

    async def _get_feat_grant_or_404(self, character_id: int, character_feat_id: int) -> CharacterFeature:
        """Fetch a feat grant scoped to the character, or raise ``CharacterFeatNotFoundException``."""

        grant = await self.feat_grant_repository.get_character_feat_by_id(character_id, character_feat_id)
        if not grant:
            raise CharacterFeatNotFoundException(character_id=character_id, character_feat_id=character_feat_id)

        return grant
