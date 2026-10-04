"""
Repository for the feat grants recorded on a character.

A feat grant is a ``character_features`` row whose ``feature.source_type ==
FEAT`` — a feat IS a Feature (see ``app/models/feature_model.py``); there is
no separate storage. The chosen ASI option (if any) is a single
``character_feature_choices`` row; the feat's effects are computed on read
from it like any other grant's (``app.features.characters.grants.effects``).
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import ASILevelChoice, CharacterFeatSource, FeatureSourceType, GrantSource
from app.core.base.repository import BaseRepository
from app.features.characters.feats.schemas import CharacterFeatResponse, FeatBriefResponse
from app.features.characters.grants.effects import GRANT_CHOICES_LOADS, build_chosen_options
from app.features.characters.grants.schemas import ChosenOptionResponse
from app.features.features.crud.repository import feature_summary_loads
from app.models.character.character_asi_choice_model import CharacterASIChoice
from app.models.character.character_feature_choice_model import CharacterFeatureChoice
from app.models.character.character_feature_model import CharacterFeature
from app.models.character.character_model import Character
from app.models.features.feature_engine_models import (
    FeatureAbilityScoreEffect,
    FeatureChoiceGroup,
    FeatureChoiceOption,
)
from app.models.features.feature_model import Feature

# Everything that is not an ASI-level pick (GM grants; feats are never AUTO-granted) is reported as GM.
_FEAT_SOURCE_BY_GRANT_SOURCE = {GrantSource.ASI: CharacterFeatSource.ASI}

# ``FeatBriefResponse.effects_summary`` reads the ``Feature`` ORM property of
# the same name, which touches every fixed-effect relationship and the
# choice-group tree — it needs the full engine effect tree, not just the bare
# relationship (see ``feature_summary_loads``).
_LOAD_OPTIONS = [*feature_summary_loads(base=selectinload(CharacterFeature.feature)), *GRANT_CHOICES_LOADS]


def to_character_feat_response(
    grant: CharacterFeature,
    effects: list[dict] | None = None,
    choices: list[ChosenOptionResponse] | None = None,
) -> CharacterFeatResponse:
    """
    Build the stable ``CharacterFeatResponse`` shape from a FEAT-source
    ``CharacterFeature`` grant. ``effects`` defaults to empty — callers that
    want the full computed picture (the player-facing listing) fetch it via
    ``app.features.characters.grants.effects`` and pass it in. ``choices``
    defaults to ``build_chosen_options(grant)`` (``grant.choices`` is
    eager-loaded by every read this repository serves) — a picked ASI option
    surfaces there like any other resolved choice group.
    """

    feat_brief = None
    if grant.feature is not None:
        feat_brief = FeatBriefResponse(
            id=grant.feature.id,
            name=grant.feature.name,
            description=grant.feature.description,
            effects_summary=grant.feature.effects_summary,
        )

    return CharacterFeatResponse(
        id=grant.id,
        character_id=grant.character_id,
        feat_id=grant.feature_id,
        source_type=_FEAT_SOURCE_BY_GRANT_SOURCE.get(grant.grant_source, CharacterFeatSource.GM),
        feat=feat_brief,
        effects=effects if effects is not None else [],
        choices=choices if choices is not None else build_chosen_options(grant),
    )


class CharacterFeatRepository(BaseRepository[CharacterFeature]):
    """
    Repository for a character's granted feats: ``character_features`` rows
    scoped to ``feature.source_type == FEAT``. Every read eager-loads the
    feature and its stored picks so grants serialize safely in the async
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
        Grant a feat to ``character``: create the ``character_features`` row
        and record the ASI pick (if any) as a ``character_feature_choices``
        row. Runs standalone (``commit=True``, GM panel) or inside a caller's
        own transaction (``commit=False``, ASI level-up).
        """

        grant = CharacterFeature(
            character_id=character.id,
            feature_id=feat_id,
            grant_source=source_type,
        )
        self.db.add(grant)
        await self.db.flush()

        await self._record_asi_pick(grant.id, await self._asi_option(ability_score_increase_id))
        await self.commit_or_flush(commit=commit)

        return await self._reload_with_feat(grant.id)

    async def set_character_feat_ability_score_increase(
        self,
        character: Character,
        grant: CharacterFeature,
        ability_score_increase_id: int | None,
        *,
        commit: bool = True,
    ) -> CharacterFeature:
        """
        Set (or clear, if ``None``) the ASI choice on an existing feat grant.
        Only the ASI group's pick is replaced — picks of the feat's other
        choice groups are kept. ``character`` is unused (kept for callers).
        """

        option = await self._asi_option(ability_score_increase_id)
        replaced_groups = [option.group_id] if option is not None else await self._asi_group_ids(grant.feature_id)

        await self.db.execute(
            delete(CharacterFeatureChoice).where(
                CharacterFeatureChoice.character_feature_id == grant.id,
                CharacterFeatureChoice.choice_group_id.in_(replaced_groups),
            )
        )
        await self.db.flush()

        await self._record_asi_pick(grant.id, option)
        await self.commit_or_flush(commit=commit)

        return await self._reload_with_feat(grant.id)

    async def _asi_option(self, ability_score_increase_id: int | None) -> FeatureChoiceOption | None:
        """The choice option carrying the ``feature_ability_score_effects`` row with this id (``None`` if absent)."""

        if ability_score_increase_id is None:
            return None

        result = await self.db.execute(
            select(FeatureChoiceOption)
            .join(FeatureAbilityScoreEffect, FeatureAbilityScoreEffect.choice_option_id == FeatureChoiceOption.id)
            .where(FeatureAbilityScoreEffect.id == ability_score_increase_id)
        )
        return result.scalars().first()

    async def _asi_group_ids(self, feature_id: int) -> list[int]:
        """Ids of the feature's choice groups whose options carry ability-score effects (its ASI groups)."""

        result = await self.db.execute(
            select(FeatureChoiceGroup.id)
            .join(FeatureChoiceOption, FeatureChoiceOption.group_id == FeatureChoiceGroup.id)
            .join(FeatureAbilityScoreEffect, FeatureAbilityScoreEffect.choice_option_id == FeatureChoiceOption.id)
            .where(FeatureChoiceGroup.feature_id == feature_id)
            .distinct()
        )
        return list(result.scalars().all())

    async def _record_asi_pick(self, grant_id: int, option: FeatureChoiceOption | None) -> None:
        """
        Store ``option`` as the grant's pick for its group. The option comes
        from an id the callers already validated
        (``validate_ability_score_increase``); ``None`` records nothing.
        """

        if option is None:
            return

        self.db.add(
            CharacterFeatureChoice(
                character_feature_id=grant_id, choice_group_id=option.group_id, choice_option_id=option.id
            )
        )
        await self.db.flush()

    async def _reload_with_feat(self, grant_id: int) -> CharacterFeature:
        """Re-fetch a grant with its feature and picks eager-loaded, discarding what the session cached before the writes."""

        result = await self.db.execute(
            select(CharacterFeature)
            .where(CharacterFeature.id == grant_id)
            .options(*_LOAD_OPTIONS)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one()

    async def remove_character_feat(self, grant: CharacterFeature, *, commit: bool = True) -> bool:
        """
        Revoke a feat grant. Cascades (``ON DELETE CASCADE`` on
        ``character_feature_id``) clear its stored picks; the feat's rows in
        the ASI-choice log are deleted with it, so the ASI level is free
        again and ``features.id`` is no longer pinned by a ``RESTRICT``
        reference.
        """

        await self.db.execute(
            delete(CharacterASIChoice).where(
                CharacterASIChoice.character_id == grant.character_id,
                CharacterASIChoice.choice_type == ASILevelChoice.FEAT,
                CharacterASIChoice.feat_id == grant.feature_id,
            )
        )
        await self.db.delete(grant)
        await self.commit_or_flush(commit=commit)
        return True

    async def remove_feats_by_source(self, character_id: int, source_type: GrantSource, *, commit: bool = True) -> None:
        """
        Revoke every feat grant of a given ``source_type`` for a character
        — a point-rebuild uses this to clear the feats granted by prior
        ASI-level choices (the caller clears their log rows). Scoped to
        FEAT-source features only; cascades clean up their stored picks.
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
