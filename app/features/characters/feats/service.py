from sqlalchemy.orm import Session

from app.features.characters.ability_score.calculator import TOTAL_FIELD_BY_ABILITY
from app.features.characters.ability_score.service import CharacterAbilityCacheService
from app.features.characters.access import get_character_for_user
from app.features.characters.core.repository import CharacterRepository
from app.features.characters.feats.exceptions import (
    CharacterFeatAlreadyKnownException,
    CharacterFeatNotFoundException,
    FeatPrerequisiteNotMetException,
    InvalidAbilityScoreIncreaseException,
)
from app.features.characters.feats.repository import CharacterFeatRepository
from app.features.characters.feats.schemas import (
    CharacterFeatAdd,
    CharacterFeatResponse,
    CharacterFeatUpdate,
)
from app.features.feats.exceptions import FeatNotFoundException
from app.features.feats.repository import FeatRepository
from app.features.users.schemas import UserResponse
from app.models.character_association_models import CharacterFeat
from app.models.character_model import Character
from app.models.feat_model import Feat


class CharacterFeatService:
    """
    Grant/revoke feats on a character, including the optional ability
    score increase choice for feats that offer one.

    Every write here (add/update/remove) refreshes the ability-score
    cache before returning, since granting or changing a feat's ASI
    choice can change the character's effective ability scores. The
    refresh itself is delegated to ``CharacterAbilityCacheService`` —
    the single point every character sub-service goes through, rather
    than each maintaining its own recalculate-and-upsert logic (see
    that class's docstring for why this was consolidated).

    Uses three collaborators:
      - ``CharacterRepository`` — access control only (fetching the
        owning character to check GM/owner permission via
        ``get_character_for_user``); no feat data lives here anymore.
      - ``CharacterFeatRepository`` — the actual ``character_feats``
        grant rows (CRUD).
      - ``CharacterAbilityCacheService`` — decides when/how to
        recompute and persist ``character_ability_scores``.
    """

    def __init__(self, db: Session):
        self.db = db
        self.repository = CharacterRepository(db)
        self.feat_grant_repository = CharacterFeatRepository(db)
        self.ability_cache_service = CharacterAbilityCacheService(db)
        self.feat_repository = FeatRepository(db)

    def get_feats(self, character_id: int, current_user: UserResponse) -> list[CharacterFeatResponse]:
        """List every feat granted to a character."""

        get_character_for_user(self.repository, character_id, current_user)

        grants = self.feat_grant_repository.get_character_feats(character_id)
        return [CharacterFeatResponse.model_validate(grant) for grant in grants]

    def add_feat(self, character_id: int, data: CharacterFeatAdd, current_user: UserResponse) -> CharacterFeatResponse:
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

        character = get_character_for_user(self.repository, character_id, current_user)

        feat = self.feat_repository.get_by_id(data.feat_id)
        if not feat:
            raise FeatNotFoundException(feat_id=data.feat_id)

        existing = self.feat_grant_repository.get_character_feat_by_feat_id(character_id, data.feat_id)
        if existing:
            raise CharacterFeatAlreadyKnownException(character_id=character_id, feat_id=data.feat_id)

        if data.ability_score_increase_id is not None:
            self._validate_ability_score_increase(feat, data.ability_score_increase_id)

        self._check_prerequisite(character, feat)

        grant = self.feat_grant_repository.add_character_feat(
            character_id, data.feat_id, data.ability_score_increase_id
        )

        self.ability_cache_service.refresh(character)

        return CharacterFeatResponse.model_validate(grant)

    def update_feat(
        self,
        character_id: int,
        character_feat_id: int,
        data: CharacterFeatUpdate,
        current_user: UserResponse,
    ) -> CharacterFeatResponse:
        """Change (or clear) the ASI choice for an already-granted feat."""

        character = get_character_for_user(self.repository, character_id, current_user)

        grant = self._get_grant_or_404(character_id, character_feat_id)

        if data.ability_score_increase_id is not None:
            feat = self.feat_repository.get_by_id(grant.feat_id)
            self._validate_ability_score_increase(feat, data.ability_score_increase_id)

        updated_grant = self.feat_grant_repository.set_character_feat_ability_score_increase(
            grant, data.ability_score_increase_id
        )

        self.ability_cache_service.refresh(character)

        return CharacterFeatResponse.model_validate(updated_grant)

    def remove_feat(self, character_id: int, character_feat_id: int, current_user: UserResponse) -> bool:
        """Revoke a feat from a character."""

        character = get_character_for_user(self.repository, character_id, current_user)

        grant = self._get_grant_or_404(character_id, character_feat_id)
        result = self.feat_grant_repository.remove_character_feat(grant)

        self.ability_cache_service.refresh(character)

        return result

    def _get_grant_or_404(self, character_id: int, character_feat_id: int) -> CharacterFeat:
        grant = self.feat_grant_repository.get_character_feat_by_id(character_id, character_feat_id)
        if not grant:
            raise CharacterFeatNotFoundException(character_id=character_id, character_feat_id=character_feat_id)
        return grant

    @staticmethod
    def _validate_ability_score_increase(feat: Feat, ability_score_increase_id: int) -> None:
        """
        Raise ``InvalidAbilityScoreIncreaseException`` unless
        ``ability_score_increase_id`` is one of ``feat``'s own
        ``ability_score_increases`` rows.
        """

        valid_ids = {increase.id for increase in feat.ability_score_increases}
        if ability_score_increase_id not in valid_ids:
            raise InvalidAbilityScoreIncreaseException(
                feat_id=feat.id, ability_score_increase_id=ability_score_increase_id
            )

    def _check_prerequisite(self, character: Character, feat: Feat) -> None:
        """
        Raise ``FeatPrerequisiteNotMetException`` if the feat has an
        ability-score prerequisite the character's current *effective*
        score doesn't meet.

        Effective scores are computed fresh here (not read from the
        cache table) so this check is always based on the character's
        current race/feats, even if the cache happens to be stale.
        """

        if feat.prerequisite_ability is None or feat.prerequisite_minimum_score is None:
            return

        totals = self.ability_cache_service.calculator.compute(character)
        field = TOTAL_FIELD_BY_ABILITY[feat.prerequisite_ability]
        actual = totals[field]

        if actual < feat.prerequisite_minimum_score:
            raise FeatPrerequisiteNotMetException(
                feat_id=feat.id,
                ability=feat.prerequisite_ability.value,
                required_minimum=feat.prerequisite_minimum_score,
                actual=actual,
            )
