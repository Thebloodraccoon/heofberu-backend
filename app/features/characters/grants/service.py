"""Character grant service: pending-choice surface and choice answering for the effect engine."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.cache import invalidate_character_cache
from app.features.characters.grants.effects import (
    build_chosen_options,
    choice_option_effect_loads,
    engine_effect_loads,
    load_feature_effect_tree,
    pending_groups,
)
from app.features.characters.grants.exceptions import (
    ChoiceCountMismatchError,
    ChoiceGroupNotFoundError,
    ChoiceOptionAlreadyPickedError,
    ChoiceOptionNotFoundError,
    GrantChoiceRequiredException,
    GrantNotFoundError,
    SkillResolutionsError,
    SpellResolutionsError,
)
from app.features.characters.grants.schemas import (
    AnsweredChoicesResponse,
    ChoiceAnswerItem,
    GrantChoicesUpdate,
    PendingChoiceGroup,
    PendingChoiceGroupsResponse,
    PendingChoiceOption,
)
from app.models.character.character_feature_choice_model import CharacterFeatureChoice
from app.models.character.character_feature_model import CharacterFeature
from app.models.character.character_model import Character
from app.models.features.feature_engine_models import FeatureChoiceGroup, FeatureChoiceOption
from app.models.features.feature_model import Feature

_CHOICE_OPTION_LOADER = selectinload(CharacterFeature.choices).selectinload(CharacterFeatureChoice.choice_option)
_ANSWERED_LOAD_OPTIONS = [
    selectinload(CharacterFeature.feature),
    _CHOICE_OPTION_LOADER,
    *choice_option_effect_loads(_CHOICE_OPTION_LOADER),
]


class FeatureGrantService:
    """
    Player-facing surface of the effect engine on a granted feature.

    A grant is fully resolved when every one of its choice groups has the
    required number of picks; until then the un-answered groups hang in
    ``get_pending_choice_groups``. Answering replaces a group's stored picks
    (a re-answer is an edit, not an append); the grant's effects are
    computed from those picks on read (``grants/effects.py``), so nothing
    else is written. All writes here never commit — callers own the
    transaction.
    """

    def __init__(self, db: AsyncSession):
        """Create the service with the stats service."""

        self.db = db
        self.stats_service = CharacterStatsService(db)

    async def _load_grant(self, character_id: int, grant_id: int) -> CharacterFeature:
        """Fetch the grant scoped to the character, or raise ``GrantNotFoundError``."""

        result = await self.db.execute(
            select(CharacterFeature).where(
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

        return {option.id: option for group in groups.values() for option in group.options}

    @staticmethod
    def _group_has_open_skill(option: FeatureChoiceOption) -> bool:
        """Whether the option carries an open ("any skill") skill effect."""

        return any(effect.skill_id is None for effect in option.skill_effects)

    @staticmethod
    def _option_has_open_spell(option: FeatureChoiceOption) -> bool:
        """Whether the option carries an open ("any spell") spell effect."""

        return any(effect.spell_id is None for effect in option.spell_effects)

    def _to_pending_response(
        self, grant: CharacterFeature, feature: Feature, pending: list[FeatureChoiceGroup]
    ) -> PendingChoiceGroupsResponse:
        """Serialise the still-pending groups of a grant."""

        return PendingChoiceGroupsResponse(
            character_feature_id=grant.id,
            feature_id=feature.id,
            feature_name=feature.name,
            groups=[
                PendingChoiceGroup(
                    id=group.id,
                    pick_count=group.pick_count,
                    choice_type=group.choice_type,
                    options=[
                        PendingChoiceOption(
                            id=option.id,
                            needs_skill=self._group_has_open_skill(option),
                            needs_spell=self._option_has_open_spell(option),
                            ability_effects=option.ability_effects,
                            skill_effects=option.skill_effects,
                            saving_throw_effects=option.saving_throw_effects,
                            armor_effects=option.armor_effects,
                            weapon_effects=option.weapon_effects,
                            spell_effects=option.spell_effects,
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

        pending = pending_groups(feature, stored)
        return self._to_pending_response(grant, feature, pending)

    async def get_all_pending_choices(self, character_id: int) -> list[PendingChoiceGroupsResponse]:
        """
        Scan every feature/feat grant on the character and return only
        the ones that still have unanswered choice groups — the
        character-wide "you still need to choose" surface, meant to drive
        a forced picker right after character creation or a level-up.

        Batches the feature-effect-tree load and the stored-choices load
        across every grant (2 queries total, not counting the fan-out
        ``selectinload`` queries) instead of looping ``load_feature_effect_tree``
        / ``_load_stored_choices`` once per grant — a character with N grants
        used to issue roughly N times the eager-load query set.
        """

        result = await self.db.execute(select(CharacterFeature).where(CharacterFeature.character_id == character_id))
        grants = list(result.scalars().unique().all())
        if not grants:
            return []

        feature_ids = {grant.feature_id for grant in grants}
        features_result = await self.db.execute(
            select(Feature).where(Feature.id.in_(feature_ids)).options(*engine_effect_loads())
        )
        feature_by_id = {feature.id: feature for feature in features_result.unique().scalars().all()}

        grant_ids = [grant.id for grant in grants]
        stored_result = await self.db.execute(
            select(CharacterFeatureChoice).where(CharacterFeatureChoice.character_feature_id.in_(grant_ids))
        )
        stored_by_grant: dict[int, list[CharacterFeatureChoice]] = {}
        for choice in stored_result.scalars().unique().all():
            stored_by_grant.setdefault(choice.character_feature_id, []).append(choice)

        pending_responses = []
        for grant in grants:
            feature = feature_by_id.get(grant.feature_id)
            if feature is None or not feature.choice_groups:
                continue

            stored = stored_by_grant.get(grant.id, [])
            pending = pending_groups(feature, stored)
            if pending:
                pending_responses.append(self._to_pending_response(grant, feature, pending))

        return pending_responses

    async def _load_grant_with_choices(self, character_id: int, grant_id: int) -> CharacterFeature:
        """Fetch the grant scoped to the character, with its stored picks (+ option effects) eager-loaded."""

        result = await self.db.execute(
            select(CharacterFeature)
            .where(
                CharacterFeature.id == grant_id,
                CharacterFeature.character_id == character_id,
            )
            .options(*_ANSWERED_LOAD_OPTIONS)
        )
        grant = result.unique().scalar_one_or_none()
        if grant is None:
            raise GrantNotFoundError(character_id=character_id, grant_id=grant_id)
        return grant

    async def get_answered_choices(self, character_id: int, grant_id: int) -> AnsweredChoicesResponse:
        """
        Return the player's resolved picks for one grant's choice groups —
        the options actually chosen, with their full effect bundle. An empty
        ``choices`` list means nothing has been answered yet (see
        ``get_pending_choice_groups`` for what's still outstanding).
        """

        grant = await self._load_grant_with_choices(character_id, grant_id)
        return AnsweredChoicesResponse(
            character_feature_id=grant.id,
            feature_id=grant.feature_id,
            feature_name=grant.feature.name,
            choices=build_chosen_options(grant),
        )

    async def get_all_answered_choices(self, character_id: int) -> list[AnsweredChoicesResponse]:
        """
        Character-wide view of every grant that has at least one answered
        choice group, with the options picked — the answered-side mirror of
        ``get_all_pending_choices``.
        """

        result = await self.db.execute(
            select(CharacterFeature)
            .where(CharacterFeature.character_id == character_id)
            .options(*_ANSWERED_LOAD_OPTIONS)
        )
        grants = list(result.unique().scalars().all())

        return [
            AnsweredChoicesResponse(
                character_feature_id=grant.id,
                feature_id=grant.feature_id,
                feature_name=grant.feature.name,
                choices=build_chosen_options(grant),
            )
            for grant in grants
            if grant.choices
        ]

    async def resolve_grant_choices(
        self,
        character: Character,
        grant: CharacterFeature,
        answers: list[ChoiceAnswerItem],
        *,
        enforce: bool = True,
    ) -> None:
        """
        Apply ``answers`` to ``grant``'s choice groups (if any).

        With ``enforce=True`` (the default), raises
        ``GrantChoiceRequiredException`` if a group is still unresolved
        afterward — level-up's newly-unlocked features and an ASI-level
        feat pick both require this: the client submits everything in one
        request, so a still-pending group means the request itself was
        incomplete and the whole write aborts (matches a missing ASI
        ``choice`` being rejected rather than defaulted).

        With ``enforce=False`` (GM-panel feat/feature grants), any given
        ``answers`` are still applied, but a still-pending group is left
        pending rather than rejected — a GM grant is allowed to land
        first and get its choice picked later via ``PATCH
        /features/{id}/choices``; ``get_all_pending_choices`` is the
        surface a client polls to know a grant still needs one.
        """

        feature = await load_feature_effect_tree(self.db, grant.feature_id)
        if feature is None or not feature.choice_groups:
            return

        if answers:
            pending_response = await self.answer_choices(character.id, grant.id, GrantChoicesUpdate(answers=answers))
            still_pending = pending_response.groups
        else:
            # No answers here doesn't mean nothing is stored yet — a feat's
            # ASI pick, for one, is written by add_character_feat's own
            # ability_score_increase_id path before this runs. Check what's
            # actually stored, not an assumed-empty grant.
            stored = await self._load_stored_choices(grant.id)
            still_pending = pending_groups(feature, stored)

        if still_pending and enforce:
            raise GrantChoiceRequiredException(
                feature_id=feature.id,
                feature_name=feature.name,
                pending_group_ids=[group.id for group in still_pending],
            )

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
        or an option carrying an open skill/spell effect — not resolvable
        yet) and replaces each answered group's stored picks. The picks'
        effects show up on the next read; only the ability-score cache and
        the character's Redis payload need refreshing here.
        """

        grant = await self._load_grant(character_id, grant_id)
        feature = await self._load_feature(grant)
        stored = await self._load_stored_choices(grant_id)

        groups = self._index_groups(feature)
        options = self._index_options(groups)

        # --- Validate the request -------------------------------------------
        answered_by_group: dict[int, list[FeatureChoiceOption]] = {}

        for item in data.answers:
            group = groups.get(item.choice_group_id)
            if group is None:
                raise ChoiceGroupNotFoundError(grant_id=grant_id, group_id=item.choice_group_id)

            option = options.get(item.choice_option_id)
            if option is None or option.group_id != group.id:
                raise ChoiceOptionNotFoundError(group_id=group.id, option_id=item.choice_option_id)

            if item.choice_option_id in {o.id for o in answered_by_group.get(group.id, [])}:
                raise ChoiceOptionAlreadyPickedError(group_id=group.id, option_id=item.choice_option_id)

            # An open ("any skill"/"any spell") option can no longer be
            # answered through the API — the system doesn't yet support
            # resolving it end to end. Existing catalog data may still carry
            # one; it's simply unpickable until that support lands.
            if self._group_has_open_skill(option):
                raise SkillResolutionsError(option_id=option.id)

            if self._option_has_open_spell(option):
                raise SpellResolutionsError(option_id=option.id)

            answered_by_group.setdefault(group.id, []).append(option)

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
            for option in picked:
                self.db.add(
                    CharacterFeatureChoice(
                        character_feature_id=grant.id,
                        choice_group_id=group_id,
                        choice_option_id=option.id,
                    )
                )

        await self.db.flush()
        stored = await self._load_stored_choices(grant_id)

        # Picks can carry ability effects — refresh the ability totals and
        # the character cache (never commits here).
        character = (await self.db.execute(select(Character).where(Character.id == character_id))).scalars().first()
        if character is not None:
            await self.stats_service.refresh(character, commit=False)
        await invalidate_character_cache(character_id)

        pending = pending_groups(feature, stored)
        return self._to_pending_response(grant, feature, pending)
