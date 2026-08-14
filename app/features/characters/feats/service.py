"""Character feat service: granting, updating, and revoking feats."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.feats.exceptions import (
    CharacterFeatAlreadyKnownException,
    CharacterFeatNotFoundException,
)
from app.features.characters.feats.repository import CharacterFeatRepository
from app.features.characters.feats.schemas import (
    CharacterFeatAdd,
    CharacterFeatResponse,
    CharacterFeatUpdate,
)
from app.features.characters.feats.validation import check_feat_prerequisite, validate_ability_score_increase
from app.features.characters.progression.feature_sync import sync_progression_features
from app.features.feats.crud.repository import FeatRepository
from app.features.feats.exceptions import FeatNotFoundException
from app.features.users.schemas import UserResponse
from app.models.character_association_models import CharacterFeat


class CharacterFeatService(CharacterSubDomainService):
    """
    Grant/revoke feats on a character, including the optional ability
    score increase choice for feats that offer one.

    Every write here (add/update/remove) refreshes the ability-score
    cache before returning, since granting or changing a feat's ASI
    choice can change the character's effective ability scores. The
    refresh itself is delegated to ``CharacterStatsService`` —
    the single point every character sub-service goes through, rather
    than each maintaining its own recalculate-and-upsert logic (see
    that class's docstring for why this was consolidated).

    Granting and revoking a feat also re-syncs the character's features
    via ``sync_progression_features``: the feat's FEAT-source features
    follow the grant in and drop off with it.

    Uses four collaborators:
      - the inherited ``CharacterSubDomainService`` — access control
        only (fetching the owning character to check GM/owner permission
        via ``get_character_for_user``); no feat data lives there.
      - ``CharacterFeatRepository`` — the actual ``character_feats``
        grant rows (CRUD).
      - ``FeatRepository`` — looking up feats and their ASI choices.
      - ``CharacterStatsService`` — decides when/how to
        recompute and persist ``character_ability_scores``.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db)
        self.feat_grant_repository = CharacterFeatRepository(db)
        self.stats_service = CharacterStatsService(db)
        self.feat_repository = FeatRepository(db)

    async def get_feats(self, character_id: int, current_user: UserResponse) -> list[CharacterFeatResponse]:
        """List every feat granted to a character."""

        await self.get_character_for_user(character_id, current_user)

        grants = await self.feat_grant_repository.get_character_feats(character_id)
        return [CharacterFeatResponse.model_validate(grant) for grant in grants]

    async def add_feat(
        self, character_id: int, data: CharacterFeatAdd, current_user: UserResponse
    ) -> CharacterFeatResponse:
        """
        Grant a feat to a character.

        Validates, in order:
          1. the feat exists;
          2. the character doesn't already have this feat (duplicates
             are rejected — see ``CharacterFeatAlreadyKnownException``);
          3. if ``ability_score_increase_id`` is given, it belongs to
             this specific feat;
          4. if the feat has a ``prerequisite_ability`` +
             ``prerequisite_minimum_score``, the character's current
             *effective* score for that ability meets it.

        Character level is intentionally not checked here — 5e ties
        feats to ASI opportunities at specific class levels, but there's
        no single universal rule for "which levels grant a feat slot"
        across every class/variant, so that's left to GM/player judgment
        for now.
        """

        character = await self.get_character_for_user(character_id, current_user)

        feat = await self.feat_repository.get_by_id(data.feat_id)
        if not feat:
            raise FeatNotFoundException(feat_id=data.feat_id)

        existing = await self.feat_grant_repository.get_character_feat_by_feat_id(character_id, data.feat_id)
        if existing:
            raise CharacterFeatAlreadyKnownException(character_id=character_id, feat_id=data.feat_id)

        if data.ability_score_increase_id is not None:
            validate_ability_score_increase(feat, data.ability_score_increase_id)

        await check_feat_prerequisite(character, feat, self.stats_service)

        grant = await self.feat_grant_repository.add_character_feat(
            character_id, data.feat_id, data.ability_score_increase_id, commit=False
        )
        await sync_progression_features(self.repository.db, character)
        await self.repository.db.commit()

        await self.stats_service.refresh(character)

        return CharacterFeatResponse.model_validate(grant)

    async def update_feat(
        self,
        character_id: int,
        character_feat_id: int,
        data: CharacterFeatUpdate,
        current_user: UserResponse,
    ) -> CharacterFeatResponse:
        """Change (or clear) the ASI choice for an already-granted feat."""

        character = await self.get_character_for_user(character_id, current_user)

        grant = await self._get_grant_or_404(character_id, character_feat_id)

        if data.ability_score_increase_id is not None:
            feat = await self.feat_repository.get_by_id(grant.feat_id)
            validate_ability_score_increase(feat, data.ability_score_increase_id)

        updated_grant = await self.feat_grant_repository.set_character_feat_ability_score_increase(
            grant, data.ability_score_increase_id
        )

        await self.stats_service.refresh(character)
        return CharacterFeatResponse.model_validate(updated_grant)

    async def remove_feat(self, character_id: int, character_feat_id: int, current_user: UserResponse) -> bool:
        """Revoke a feat from a character (its FEAT-source features drop off with it)."""

        character = await self.get_character_for_user(character_id, current_user)

        grant = await self._get_grant_or_404(character_id, character_feat_id)
        result = await self.feat_grant_repository.remove_character_feat(grant)
        await sync_progression_features(self.repository.db, character)
        await self.repository.db.commit()

        await self.stats_service.refresh(character)

        return result

    async def _get_grant_or_404(self, character_id: int, character_feat_id: int) -> CharacterFeat:
        """Fetch a feat grant scoped to the character, or raise ``CharacterFeatNotFoundException``."""

        grant = await self.feat_grant_repository.get_character_feat_by_id(character_id, character_feat_id)
        if not grant:
            raise CharacterFeatNotFoundException(character_id=character_id, character_feat_id=character_feat_id)

        return grant
