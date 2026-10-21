"""Applying an ASI-level choice (Ability Score Improvement or feat) and recording it in the ASI log."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ASILevelChoice, GrantSource
from app.features.characters.feats.exceptions import CharacterFeatAlreadyKnownException
from app.features.characters.feats.repository import CharacterFeatRepository
from app.features.characters.feats.validation import ensure_feat_min_level, ensure_prerequisite_met
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
        reuse_asi_grant: bool = False,
    ) -> CharacterFeature:
        """
        Apply a feat-as-ASI: the feat must exist, not be known yet, be
        takeable at ``class_level`` (``min_level``) and its prerequisite must
        be met. Then it is granted (``grant_source=ASI``) and the choice is
        logged. The feat is only *taken* here: every choice group of it — its
        ability-score pick included — is answered afterwards like any other
        grant's (``GET /grants/pending`` + ``PATCH .../choices``), the one
        place choices are made.

        With ``reuse_asi_grant`` (a rebuild re-taking a feat it already had
        from an ASI level) the existing ASI grant is kept with its picks
        instead of being granted anew. ``totals`` is not advanced: a feat's
        own effects are only known after the grant is flushed.
        """

        feat = await self.feat_repository.get_by_id(choice.feat_id)
        if not feat:
            raise FeatNotFoundException(feat_id=choice.feat_id)

        existing = await self.feat_grant_repository.get_character_feat_by_feat_id(character.id, choice.feat_id)
        reused = existing is not None and reuse_asi_grant and existing.grant_source == GrantSource.ASI
        if existing is not None and not reused:
            raise CharacterFeatAlreadyKnownException(character_id=character.id, feat_id=choice.feat_id)

        ensure_feat_min_level(feat, class_level)
        ensure_prerequisite_met(feat, totals)

        grant = existing if reused else await self.feat_grant_repository.add_character_feat(
            character, choice.feat_id, None, source_type=GrantSource.ASI
        )
        await self.asi_repository.add(character.id, class_level, ASILevelChoice.FEAT, feat_id=choice.feat_id)

        return grant
