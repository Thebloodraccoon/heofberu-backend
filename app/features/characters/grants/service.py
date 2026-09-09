"""Character grant service: pending-choice surface and choice answering for the effect engine."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.cache import invalidate_character_cache
from app.features.characters.grants.exceptions import (
    ChoiceCountMismatchError,
    ChoiceGroupNotFoundError,
    ChoiceOptionAlreadyPickedError,
    ChoiceOptionNotFoundError,
    GrantNotFoundError,
    SkillResolutionsError,
)
from app.features.characters.grants.materializer import (
    FeatureGrantMaterializer,
    ResolvedOption,
    load_feature_effect_tree,
)
from app.features.characters.grants.schemas import (
    GrantChoicesUpdate,
    PendingChoiceGroup,
    PendingChoiceGroupsResponse,
    PendingChoiceOption,
)
from app.models.character_engine_models import CharacterFeatureChoice
from app.models.character_feature_model import CharacterFeature
from app.models.character_model import Character
from app.models.feature_engine_models import FeatureChoiceGroup, FeatureChoiceOption
from app.models.feature_model import Feature


class FeatureGrantService:
    """
    Player-facing surface of the effect engine on a granted feature.

    A grant is "fully materialized" when every one of its choice groups has
    the required number of picks; until then the un-answered groups hang in
    ``get_pending_choice_groups``. Answering replaces a group's stored picks
    (a re-answer is an edit, not an append) and re-materializes the grant's
    effect rows in the same transaction. All writes here never commit —
    callers own the transaction (the fixed abilities are re-counted by the
    stats service, and the character cache is refreshed by the caller).
    """

    def __init__(self, db: AsyncSession):
        """Create the service with the materializer and the stats service."""

        self.db = db
        self.materializer = FeatureGrantMaterializer()
        self.stats_service = CharacterStatsService(db)

    async def _load_grant(self, character_id: int, grant_id: int) -> CharacterFeature:
        """Fetch the grant scoped to the character, or raise ``GrantNotFoundError``."""

        result = await self.db.execute(
            select(CharacterFeature)
            .where(
                CharacterFeature.id == grant_id,
                CharacterFeature.character_id == character_id,
            )
        )
        grant = result.scalar_one_or_none()
        if grant is None:
            raise GrantNotFoundError(character_id=character_id, grant_id=grant_id)
        return grant

    async def _load_feature(self, grant: CharacterFeature) -> Feature:
        """Fetch the grant's feature with its full engine effect tree."""

        feature = await load_feature_effect_tree(self.db, grant.feature_id)
        if feature is None:
            raise GrantNotFoundError(
                character_id=grant.character_id,
                grant_id=grant.id,
            )
        return feature

    async def _load_stored_choices(self, grant_id: int) -> list[CharacterFeatureChoice]:
        """Fetch the grant's stored picks."""

        result = await self.db.execute(
            select(CharacterFeatureChoice).where(CharacterFeatureChoice.character_feature_id == grant_id)
        )
        return list(result.scalars().unique().all())

    def _index_groups(self, feature: Feature) -> dict[int, FeatureChoiceGroup]:
        """``{group_id: group}`` for the feature's choice groups."""

        return {group.id: group for group in feature.choice_groups}

    def _index_options(self, groups: dict[int, FeatureChoiceGroup]) -> dict[int, FeatureChoiceOption]:
        """``{option_id: option}`` across every group of the feature."""

        return {
            option.id: option for group in groups.values() for option in group.options
        }

    @staticmethod
    def _group_has_open_skill(option: FeatureChoiceOption) -> bool:
        """Whether the option carries an open ("any skill") skill effect."""

        return any(effect.skill_id is None for effect in option.skill_effects)

    def _to_pending_response(self, grant: CharacterFeature, feature: Feature, pending: list[FeatureChoiceGroup]) -> PendingChoiceGroupsResponse:
        """Serialise the still-pending groups of a grant."""

        return PendingChoiceGroupsResponse(
            character_feature_id=grant.id,
            feature_id=feature.id,
            feature_name=feature.name,
            groups=[
                PendingChoiceGroup(
                    id=group.id,
                    pick_count=group.pick_count,
                    label=group.label,
                    options=[
                        PendingChoiceOption(
                            id=option.id,
                            label=option.label,
                            needs_skill=self._group_has_open_skill(option),
                        )
                        for option in group.options
                    ],
                )
                for group in pending
            ],
        )

    async def get_pending_choice_groups(self, character_id: int, grant_id: int) -> PendingChoiceGroupsResponse:
        """Return the grant's choice groups that still need the player's picks."""

        grant = await self._load_grant(character_id, grant_id)
        feature = await self._load_feature(grant)
        stored = await self._load_stored_choices(grant_id)

        pending = self.materializer.pending_groups(feature, stored)
        return self._to_pending_response(grant, feature, pending)

    async def answer_choices(
        self,
        character_id: int,
        grant_id: int,
        data: GrantChoicesUpdate,
    ) -> PendingChoiceGroupsResponse:
        """
        Answer the grant's pending choice groups (full replace per group).

        Validates the request against the feature's groups/options (wrong
        group, unknown or foreign option, duplicate pick, wrong pick count,
        missing skill resolution), replaces each answered group's stored
        picks, and re-materializes the grant's effect rows from the full
        stored choice set in the same transaction.
        """

        grant = await self._load_grant(character_id, grant_id)
        feature = await self._load_feature(grant)
        stored = await self._load_stored_choices(grant_id)

        groups = self._index_groups(feature)
        options = self._index_options(groups)

        # --- Validate the request -------------------------------------------
        answered_by_group: dict[int, list[tuple[FeatureChoiceOption, int | None]]] = {}

        for item in data.answers:
            group = groups.get(item.choice_group_id)
            if group is None:
                raise ChoiceGroupNotFoundError(grant_id=grant_id, group_id=item.choice_group_id)

            option = options.get(item.choice_option_id)
            if option is None or option.group_id != group.id:
                raise ChoiceOptionNotFoundError(group_id=group.id, option_id=item.choice_option_id)

            if item.choice_option_id in {o.id for o, _ in answered_by_group.get(group.id, [])}:
                raise ChoiceOptionAlreadyPickedError(group_id=group.id, option_id=item.choice_option_id)

            if self._group_has_open_skill(option) and item.skill_id is None:
                raise SkillResolutionsError(option_id=option.id)

            answered_by_group.setdefault(group.id, []).append((option, item.skill_id))

        for group in groups.values():
            chosen = answered_by_group.get(group.id, [])
            if chosen and len(chosen) != group.pick_count:
                raise ChoiceCountMismatchError(group_id=group.id, pick_count=group.pick_count, given=len(chosen))

        # --- Persist (replace per group) ------------------------------------
        answered_group_ids = list(answered_by_group)
        if answered_group_ids:
            await self.db.execute(
                delete(CharacterFeatureChoice).where(
                    CharacterFeatureChoice.character_feature_id == grant.id,
                    CharacterFeatureChoice.choice_group_id.in_(answered_group_ids),
                )
            )
            await self.db.flush()

        for group_id, picked in answered_by_group.items():
            for option, _skill_id in picked:
                self.db.add(
                    CharacterFeatureChoice(
                        character_feature_id=grant.id,
                        choice_group_id=group_id,
                        choice_option_id=option.id,
                    )
                )

        # --- Re-materialize from the full stored set -------------------------
        await self.db.flush()
        stored = await self._load_stored_choices(grant_id)

        choice_map: dict[int, list[ResolvedOption]] = {}
        resolution_by_option = {
            option.id: skill_id for _, picked in answered_by_group.items() for option, skill_id in picked
        }
        for choice in stored:
            option = options.get(choice.choice_option_id)
            if option is None:
                continue
            choice_map.setdefault(choice.choice_group_id, []).append(
                ResolvedOption(option=option, skill_id=resolution_by_option.get(option.id))
            )

        await self.materializer.reconcile(self.db, character_id, grant, feature, choice_map)
        await self.db.flush()

        # The player's picks changed the fixed-effects surface — refresh the
        # ability totals and the character cache (never commits here).
        character = (
            await self.db.execute(select(Character).where(Character.id == character_id))
        ).scalars().first()
        if character is not None:
            await self.stats_service.refresh(character, commit=False)
        await invalidate_character_cache(character_id)

        pending = self.materializer.pending_groups(feature, stored)
        return self._to_pending_response(grant, feature, pending)
