"""
Repository for the feat grants recorded on a character.

A feat grant is a ``character_features`` row whose ``feature.source_type ==
FEAT`` — a feat IS a Feature (see ``app/models/feature_model.py``); there is
no separate storage. The chosen ASI option (if any) is a single
``character_feature_choices`` row, materialized into the character's
skill/save/armor/weapon/spell rows the same way any other feature grant is
(``app.features.characters.progression.feature_sync.materialize_grant``).
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import CharacterFeatSource, FeatureSourceType, GrantSource
from app.core.base.repository import BaseRepository
from app.features.characters.progression.feature_sync import materialize_grant
from app.features.characters.schemas import (
    CharacterFeatResponse,
    FeatAbilityScoreIncreaseResponse,
    FeatBriefResponse,
)
from app.models.character_engine_models import CharacterFeatureChoice
from app.models.character_feature_model import CharacterFeature
from app.models.character_model import Character
from app.models.feature_engine_models import FeatureAbilityScoreEffect, FeatureChoiceOption
from app.models.feature_model import Feature

_GRANT_SOURCE_TO_FEAT_SOURCE = {
    GrantSource.GM: CharacterFeatSource.GM,
    GrantSource.ASI: CharacterFeatSource.ASI,
    GrantSource.AUTO: CharacterFeatSource.GM,  # feats are never AUTO-granted; defensive fallback only.
}

_LOAD_OPTIONS = [
    selectinload(CharacterFeature.feature),
    selectinload(CharacterFeature.choices)
    .selectinload(CharacterFeatureChoice.choice_option)
    .selectinload(FeatureChoiceOption.ability_effects),
]


def to_character_feat_response(grant: CharacterFeature) -> CharacterFeatResponse:
    """Build the stable ``CharacterFeatResponse`` shape from a FEAT-source ``CharacterFeature`` grant."""

    ability_score_increase_id: int | None = None
    ability_score_increase: FeatAbilityScoreIncreaseResponse | None = None

    if grant.choices:
        option = grant.choices[0].choice_option
        effect = option.ability_effects[0] if option is not None and option.ability_effects else None
        if effect is not None:
            ability_score_increase_id = effect.id
            ability_score_increase = FeatAbilityScoreIncreaseResponse(
                id=effect.id, ability=effect.ability, amount=effect.amount
            )

    feat_brief = None
    if grant.feature is not None:
        feat_brief = FeatBriefResponse(id=grant.feature.id, name=grant.feature.name, description=grant.feature.description)

    return CharacterFeatResponse(
        id=grant.id,
        character_id=grant.character_id,
        feat_id=grant.feature_id,
        ability_score_increase_id=ability_score_increase_id,
        source_type=_GRANT_SOURCE_TO_FEAT_SOURCE.get(grant.grant_source, CharacterFeatSource.GM),
        feat=feat_brief,
        ability_score_increase=ability_score_increase,
    )


class CharacterFeatRepository(BaseRepository[CharacterFeature]):
    """
    Repository for a character's granted feats: ``character_features`` rows
    scoped to ``feature.source_type == FEAT``. Every read eager-loads the
    feature and its stored choice so grants serialize safely in the async
    session.
    """

    def __init__(self, db: AsyncSession):
        """Create the feat-grant repository."""

        super().__init__(CharacterFeature, db)

    async def get_character_feats(self, character_id: int) -> list[CharacterFeature]:
        """Get every feat grant for a character."""

        result = await self.db.execute(
            select(CharacterFeature)
            .join(Feature, Feature.id == CharacterFeature.feature_id)
            .where(CharacterFeature.character_id == character_id, Feature.source_type == FeatureSourceType.FEAT)
            .options(*_LOAD_OPTIONS)
        )
        return list(result.scalars().unique().all())

    async def get_character_feat_by_id(self, character_id: int, character_feat_id: int) -> CharacterFeature | None:
        """Fetch a single feat grant by its own id, scoped to the character."""

        result = await self.db.execute(
            select(CharacterFeature)
            .join(Feature, Feature.id == CharacterFeature.feature_id)
            .where(
                CharacterFeature.id == character_feat_id,
                CharacterFeature.character_id == character_id,
                Feature.source_type == FeatureSourceType.FEAT,
            )
            .options(*_LOAD_OPTIONS)
        )
        return result.scalar_one_or_none()

    async def get_character_feat_by_feat_id(self, character_id: int, feat_id: int) -> CharacterFeature | None:
        """Fetch a character's grant for a specific feat, if any (used for duplicate checks)."""

        result = await self.db.execute(
            select(CharacterFeature).where(
                CharacterFeature.character_id == character_id,
                CharacterFeature.feature_id == feat_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_character_feat(
        self,
        character: Character,
        feat_id: int,
        ability_score_increase_id: int | None,
        *,
        source_type: GrantSource = GrantSource.GM,
        commit: bool = True,
    ) -> CharacterFeature:
        """
        Grant a feat to ``character``: create the ``character_features`` row,
        record the ASI pick (if any) as a ``character_feature_choices`` row,
        then materialize every effect the feat carries (the picked ASI
        option plus any fixed skill/save/armor/weapon/spell effects) onto
        the character. Never commits internally except the final write, so
        this can run standalone (``commit=True``, GM panel) or inside a
        caller's own ``_atomic()`` (``commit=False``, ASI level-up).
        """

        grant = CharacterFeature(
            character_id=character.id,
            feature_id=feat_id,
            grant_source=source_type,
            notes="",
        )
        self.db.add(grant)
        await self.db.flush()

        if ability_score_increase_id is not None:
            effect = await self.db.get(FeatureAbilityScoreEffect, ability_score_increase_id)
            option = await self.db.get(FeatureChoiceOption, effect.choice_option_id) if effect is not None else None
            if effect is not None and option is not None:
                self.db.add(
                    CharacterFeatureChoice(
                        character_feature_id=grant.id,
                        choice_group_id=option.group_id,
                        choice_option_id=option.id,
                    )
                )
                await self.db.flush()

        await materialize_grant(self.db, character, grant)
        await self.commit_or_flush(commit=commit)

        return await self._reload_with_feat(grant.id)

    async def set_character_feat_ability_score_increase(
        self, character: Character, grant: CharacterFeature, ability_score_increase_id: int | None
    ) -> CharacterFeature:
        """Set (or clear, if ``None``) the ASI choice on an existing feat grant, re-materializing its effects."""

        await self.db.execute(
            delete(CharacterFeatureChoice).where(CharacterFeatureChoice.character_feature_id == grant.id)
        )
        await self.db.flush()

        if ability_score_increase_id is not None:
            effect = await self.db.get(FeatureAbilityScoreEffect, ability_score_increase_id)
            option = await self.db.get(FeatureChoiceOption, effect.choice_option_id) if effect is not None else None
            if effect is not None and option is not None:
                self.db.add(
                    CharacterFeatureChoice(
                        character_feature_id=grant.id,
                        choice_group_id=option.group_id,
                        choice_option_id=option.id,
                    )
                )
                await self.db.flush()

        await materialize_grant(self.db, character, grant)
        await self.commit_or_flush()

        return await self._reload_with_feat(grant.id)

    async def _reload_with_feat(self, grant_id: int) -> CharacterFeature:
        """Re-fetch a grant with its feature and choice eager-loaded (for safe serialization)."""

        result = await self.db.execute(
            select(CharacterFeature).where(CharacterFeature.id == grant_id).options(*_LOAD_OPTIONS)
        )
        return result.scalar_one()

    async def remove_character_feat(self, grant: CharacterFeature) -> bool:
        """
        Revoke a feat grant. Cascades (``ON DELETE CASCADE`` on
        ``source_character_feature_id`` / ``character_feature_id``) clear
        its stored choice and every materialized effect row automatically.
        """

        await self.db.delete(grant)
        await self.commit_or_flush()
        return True

    async def remove_feats_by_source(
        self, character_id: int, source_type: GrantSource, *, commit: bool = True
    ) -> None:
        """
        Revoke every feat grant of a given ``source_type`` for a character
        — a point-rebuild uses this to clear the feats granted by prior
        ASI-level choices before replacing them. Scoped to FEAT-source
        features only. Cascades clean up their materialized effect rows.
        """

        await self.db.execute(
            delete(CharacterFeature).where(
                CharacterFeature.character_id == character_id,
                CharacterFeature.grant_source == source_type,
                CharacterFeature.feature_id.in_(
                    select(Feature.id).where(Feature.source_type == FeatureSourceType.FEAT)
                ),
            )
        )
        await self.commit_or_flush(commit=commit)
