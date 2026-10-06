"""Applying an ASI-level choice (Ability Score Improvement or feat) and recording it in the ASI log."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ASILevelChoice, GrantSource
from app.features.characters.feats.exceptions import CharacterFeatAlreadyKnownException
from app.features.characters.feats.repository import CharacterFeatRepository
from app.features.characters.feats.validation import (
    ensure_feat_asi_within_cap,
    ensure_feat_min_level,
    ensure_prerequisite_met,
    validate_ability_score_increase,
    validate_asi_choice_required,
)
from app.features.characters.progression.repository import CharacterASIChoiceRepository
from app.features.characters.progression.rules import apply_asi_to_totals
from app.features.characters.progression.schemas import ASIIncreaseItem, FeatChoice
from app.features.feats.crud.repository import FeatRepository
from app.features.feats.exceptions import FeatNotFoundException
from app.models.character.character_feature_model import CharacterFeature
from app.models.character.character_model import Character


class AsiChoiceService:
    """
    Resolves one ASI level: either the ability increments or a feat taken
    instead. Both validate against the character's *effective* ability
    totals, which the caller computes once and passes in. Flush only —
    callers own the transaction.
    """

    def __init__(self, db: AsyncSession):
        """Create the repositories the ASI-level flows write through."""

        self.feat_repository = FeatRepository(db)
        self.feat_grant_repository = CharacterFeatRepository(db)
        self.asi_repository = CharacterASIChoiceRepository(db)

    async def apply_asi(
        self, character: Character, increases: list[ASIIncreaseItem], class_level: int, totals: dict[str, int]
    ) -> None:
        """
        Apply an Ability Score Improvement: no ability's effective total may
        pass the standard cap of 20 (player choices are capped there even
        when a feature's ``new_cap`` lets a score reach 30 via GM
        intervention), then the choice is logged. The base columns are NOT
        touched — increments live only in the ``character_asi_choices`` log
        and are counted from there. ``totals`` is advanced in place so a
        following choice in the same operation sees this one.
        """

        apply_asi_to_totals(totals, increases)

        await self.asi_repository.add(
            character.id,
            class_level,
            ASILevelChoice.ASI,
            increases=[{"ability": item.ability.value, "amount": item.amount} for item in increases],
        )

    async def apply_feat(
        self,
        character: Character,
        choice: FeatChoice,
        class_level: int,
        totals: dict[str, int],
        *,
        require_asi_pick: bool = False,
    ) -> CharacterFeature:
        """
        Apply a feat-as-ASI: the feat must exist, not be known yet, be
        takeable at ``class_level`` (``min_level``), have a valid ASI pick
        (required when ``require_asi_pick``) that keeps the score within the
        cap of 20, and its prerequisite must be met. Then it is granted
        (``grant_source=ASI``), the choice is logged, and the grant is
        returned so the caller can enforce the feat's OTHER choice groups
        like a newly unlocked feature's. ``totals`` is not advanced: a feat's
        own fixed effects are only known after the grant is flushed.
        """

        feat = await self.feat_repository.get_by_id(choice.feat_id)
        if not feat:
            raise FeatNotFoundException(feat_id=choice.feat_id)

        if await self.feat_grant_repository.get_character_feat_by_feat_id(character.id, choice.feat_id):
            raise CharacterFeatAlreadyKnownException(character_id=character.id, feat_id=choice.feat_id)

        ensure_feat_min_level(feat, class_level)
        if require_asi_pick:
            validate_asi_choice_required(feat, choice.ability_score_increase_id)
        validate_ability_score_increase(feat, choice.ability_score_increase_id)
        ensure_feat_asi_within_cap(feat, choice.ability_score_increase_id, totals)
        ensure_prerequisite_met(feat, totals)

        grant = await self.feat_grant_repository.add_character_feat(
            character,
            choice.feat_id,
            choice.ability_score_increase_id,
            source_type=GrantSource.ASI,
        )
        await self.asi_repository.add(
            character.id,
            class_level,
            ASILevelChoice.FEAT,
            feat_id=choice.feat_id,
            ability_score_increase_id=choice.ability_score_increase_id,
        )

        return grant
