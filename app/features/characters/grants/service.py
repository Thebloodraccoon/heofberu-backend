"""Character grant service: pending-choice surface and choice answering for the effect engine."""

from collections.abc import Iterable
from typing import NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ABILITY_SCORE_CAP, AbilityScore, ChoiceType
from app.features.characters.ability_score.calculator import TOTAL_FIELD_BY_ABILITY
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.features.repository import CharacterFeatureRepository
from app.features.characters.grants.effects import (
    GrantEffects,
    build_chosen_options,
    grant_effects,
    load_character_grant_effects_by_grant,
    load_feature_effect_trees,
    pending_groups,
    stored_picks,
)
from app.features.characters.grants.exceptions import (
    AbilityPickCapExceededError,
    AbilityPickNotAllowedError,
    AbilityPickRequiredError,
    ChoiceCountMismatchError,
    ChoiceGroupNotFoundError,
    ChoiceOptionAlreadyPickedError,
    ChoiceOptionNotFoundError,
    GrantChoiceRequiredException,
    GrantNotFoundError,
    SkillPickNotAllowedError,
    SkillPickRequiredError,
    SpellPickNotAllowedError,
    SpellPickRequiredError,
    UnexpectedAbilityPickError,
    UnexpectedSkillPickError,
    UnexpectedSpellPickError,
    UnknownSkillPickError,
    UnknownSpellPickError,
)
from app.features.characters.grants.schemas import (
    AnsweredChoicesResponse,
    ChoiceAnswerItem,
    GrantChoicesUpdate,
    PendingChoiceGroup,
    PendingChoiceGroupsResponse,
    PendingChoiceOption,
    PendingChoicesCountResponse,
    SpellPickCandidate,
)
from app.features.characters.grants.repository import GrantRulesRepository
from app.features.characters.grants.skill_rules import (
    SkillBaseline,
    SkillSources,
    apply_option,
    build_skill_sources,
    option_refusal,
)
from app.features.characters.grants.spell_rules import (
    SpellFacts,
    SpellOwnership,
    SpellSources,
    allowed_spells,
    build_spell_sources,
    open_spell_effect,
    spell_refusal,
)
from app.features.characters.proficiencies.repository import CharacterProficiencyRepository
from app.features.users.schemas import UserResponse
from app.models.character.character_feature_choice_model import CharacterFeatureChoice
from app.models.character.character_feature_model import CharacterFeature
from app.models.character.character_model import Character
from app.models.features.feature_engine_models import FeatureChoiceGroup, FeatureChoiceOption, effect_groups
from app.models.features.feature_model import Feature


def _option_has_open_skill(option: FeatureChoiceOption) -> bool:
    """Whether the option carries an open ("any skill") skill effect."""

    return any(effect.skill_id is None for effect in option.skill_effects)


def _option_has_open_spell(option: FeatureChoiceOption) -> bool:
    """Whether the option carries an open ("any spell") spell effect."""

    return any(effect.spell_id is None for effect in option.spell_effects)


def _ability_rows(option: FeatureChoiceOption) -> list:
    """The option's ability-score and saving-throw rows (a group carries one of the two types)."""

    return [*option.ability_effects, *option.saving_throw_effects]


def _option_has_open_ability(option: FeatureChoiceOption) -> bool:
    """Whether the option carries an open ("any ability" / "any saving throw") effect."""

    return any(effect.ability is None for effect in _ability_rows(option))


class OptionPick(NamedTuple):
    """One validated pick: the option and, for an open option, the skill/spell/ability named for it."""

    option: FeatureChoiceOption
    skill_id: int | None = None
    spell_id: int | None = None
    ability: AbilityScore | None = None


def _skill_availability(
    option: FeatureChoiceOption, baseline: SkillBaseline | None, all_skill_ids: list[int]
) -> tuple[list[int] | None, bool]:
    """``(allowed_skill_ids, available)`` of a pending option (no baseline = not a SKILL group: no limits)."""

    if baseline is None:
        return None, True

    if _option_has_open_skill(option):
        allowed = [skill_id for skill_id in all_skill_ids if option_refusal(option, skill_id, baseline) is None]
        return allowed, bool(allowed)

    return None, option_refusal(option, None, baseline) is None


def _spell_availability(
    option: FeatureChoiceOption, candidates: list[SpellFacts] | None, ownership: SpellOwnership | None
) -> tuple[list[SpellPickCandidate] | None, bool]:
    """``(allowed_spells, available)`` of a pending option (only an open spell option is limited)."""

    if candidates is None or ownership is None or not _option_has_open_spell(option):
        return None, True

    allowed = [
        SpellPickCandidate.model_validate(spell, from_attributes=True)
        for spell in allowed_spells(option, candidates, ownership)
    ]
    return allowed, bool(allowed)


def _to_pending_response(
    grant: CharacterFeature,
    feature: Feature,
    pending: list[FeatureChoiceGroup],
    baseline: SkillBaseline | None = None,
    all_skill_ids: list[int] | None = None,
    spell_candidates: list[SpellFacts] | None = None,
    spell_ownership: SpellOwnership | None = None,
) -> PendingChoiceGroupsResponse:
    """
    Serialise the still-pending groups of a grant. With a ``baseline`` the options of its SKILL groups carry
    ``allowed_skill_ids``/``available``; with spell candidates + ownership its open spell options carry
    ``allowed_spells``/``available`` (see :meth:`FeatureGrantService._pending_response`).
    """

    def option_response(group: FeatureChoiceGroup, option: FeatureChoiceOption) -> PendingChoiceOption:
        if group.choice_type == ChoiceType.SPELL:
            allowed_skill_ids = None
            spells, available = _spell_availability(option, spell_candidates, spell_ownership)
        else:
            group_baseline = baseline if group.choice_type == ChoiceType.SKILL else None
            allowed_skill_ids, available = _skill_availability(option, group_baseline, all_skill_ids or [])
            spells = None
        # ORM effect rows are validated into the response items by attribute
        return PendingChoiceOption.model_validate(
            {
                "id": option.id,
                "needs_skill": _option_has_open_skill(option),
                "needs_spell": _option_has_open_spell(option),
                "needs_ability": _option_has_open_ability(option),
                "allowed_skill_ids": allowed_skill_ids,
                "allowed_spells": spells,
                "available": available,
                "effects": effect_groups(option),
            },
            from_attributes=True,
        )

    return PendingChoiceGroupsResponse(
        character_feature_id=grant.id,
        feature_id=feature.id,
        feature_name=feature.name,
        groups=[
            PendingChoiceGroup(
                id=group.id,
                pick_count=group.pick_count,
                choice_type=group.choice_type,
                options=[option_response(group, option) for option in group.options],
            )
            for group in pending
        ],
    )


def _has_skill_group(groups: list[FeatureChoiceGroup]) -> bool:
    return any(group.choice_type == ChoiceType.SKILL for group in groups)


def _has_open_spell_option(groups: list[FeatureChoiceGroup]) -> bool:
    return any(_option_has_open_spell(option) for group in groups for option in group.options)


def _own_effects(
    feature: Feature, stored: list[CharacterFeatureChoice], excluded_group_ids: set[int]
) -> GrantEffects:
    """The grant's effects from its fixed rows and its stored picks outside ``excluded_group_ids``."""

    kept = (choice for choice in stored if choice.choice_group_id not in excluded_group_ids)
    return grant_effects(feature, stored_picks(kept))


def _to_answered_response(grant: CharacterFeature) -> AnsweredChoicesResponse:
    """Serialise a grant's stored picks (``feature`` and ``choices`` eager-loaded)."""

    return AnsweredChoicesResponse(
        character_feature_id=grant.id,
        feature_id=grant.feature_id,
        feature_name=grant.feature.name,
        choices=build_chosen_options(grant),
    )


def _validate_answers(
    grant_id: int, feature: Feature, answers: Iterable[ChoiceAnswerItem]
) -> dict[int, list[OptionPick]]:
    """
    Check ``answers`` against the feature's groups/options and return the
    picks per group. Raises on a wrong group, an unknown or foreign option,
    a duplicate pick (the same option — for an open option, with the same
    skill/spell/ability), a wrong pick count, a ``skill_id``/``spell_id``/``ability``
    missing on an open ("any skill/spell/ability") option or set on any other,
    or an ``ability`` the option already names. Whether the skills/spells exist
    and fit the character is checked by the service.
    """

    groups = {group.id: group for group in feature.choice_groups}
    options = {option.id: option for group in feature.choice_groups for option in group.options}
    answered: dict[int, list[OptionPick]] = {}

    for item in answers:
        group = groups.get(item.choice_group_id)
        if group is None:
            raise ChoiceGroupNotFoundError(grant_id=grant_id, group_id=item.choice_group_id)

        option = options.get(item.choice_option_id)
        if option is None or option.group_id != group.id:
            raise ChoiceOptionNotFoundError(group_id=group.id, option_id=item.choice_option_id)

        if _option_has_open_skill(option):
            if item.skill_id is None:
                raise SkillPickRequiredError(option_id=option.id)
        elif item.skill_id is not None:
            raise UnexpectedSkillPickError(option_id=option.id)

        if _option_has_open_spell(option):
            if item.spell_id is None:
                raise SpellPickRequiredError(option_id=option.id)
        elif item.spell_id is not None:
            raise UnexpectedSpellPickError(option_id=option.id)

        if _option_has_open_ability(option):
            if item.ability is None:
                raise AbilityPickRequiredError(option_id=option.id)
            if any(effect.ability == item.ability for effect in _ability_rows(option)):
                raise AbilityPickNotAllowedError(option_id=option.id, ability=item.ability.value)
        elif item.ability is not None:
            raise UnexpectedAbilityPickError(option_id=option.id)

        pick = OptionPick(option, item.skill_id, item.spell_id, item.ability)
        picked = answered.setdefault(group.id, [])
        if any(other.option.id == option.id and other[1:] == pick[1:] for other in picked):
            raise ChoiceOptionAlreadyPickedError(group_id=group.id, option_id=option.id)

        picked.append(pick)

    for group_id, picked in answered.items():
        if len(picked) != groups[group_id].pick_count:
            raise ChoiceCountMismatchError(group_id=group_id, pick_count=groups[group_id].pick_count, given=len(picked))

    return answered


class FeatureGrantService(CharacterSubDomainService):
    """
    Player-facing surface of the effect engine on a granted feature.

    A grant is fully resolved when every one of its choice groups has the
    required number of picks; until then the un-answered groups hang in
    ``get_pending_choice_groups``. Answering replaces a group's stored picks
    (a re-answer is an edit, not an append); the grant's effects are
    computed from those picks on read (``grants/effects.py``), so nothing
    else is written.

    The public read/answer methods take the acting user and enforce
    GM/owner access here. :meth:`resolve_grant_choices` /
    :meth:`resolve_grants_choices` are the internal building blocks for
    callers that already hold a transaction and an authorized character
    (level-up, the GM panel): they only flush, never refresh stats or
    invalidate the cache — the caller (inside its atomic block) does.
    """

    def __init__(self, db: AsyncSession):
        """Create the service with the stats service."""

        super().__init__(db)
        self.db = db
        self.grant_repository = CharacterFeatureRepository(db)
        self.rules_repository = GrantRulesRepository(db)
        self.proficiency_repository = CharacterProficiencyRepository(db)
        self.stats_service = CharacterStatsService(db)

    def _context(self, character_id: int, *, flush_first: bool = False) -> "_RulesContext":
        """A fresh :class:`_RulesContext` for one request (``flush_first`` on write paths)."""

        return _RulesContext(self, character_id, flush_first=flush_first)

    async def _load_grant(
        self, character_id: int, grant_id: int, *, for_update: bool = False, with_answers: bool = False
    ) -> CharacterFeature:
        """Fetch the grant scoped to the character, or raise ``GrantNotFoundError``."""

        grant = await self.grant_repository.get_grant(
            character_id, grant_id, for_update=for_update, with_answers=with_answers
        )
        if grant is None:
            raise GrantNotFoundError(character_id=character_id, grant_id=grant_id)
        return grant

    async def _load_trees(self, grants: list[CharacterFeature], *, only_with_choices: bool) -> dict[int, Feature]:
        """
        Effect trees of the grants' features, one batched load. With
        ``only_with_choices`` features without choice groups (the
        denormalized ``has_choices`` flag) are skipped without loading.
        """

        feature_ids = {grant.feature_id for grant in grants}
        if only_with_choices:
            feature_ids = await self.grant_repository.filter_features_with_choices(feature_ids)

        # the choices surface shows an open spell option's filter with its class names
        return await load_feature_effect_trees(self.db, feature_ids, with_spell_filters=True)

    async def _load_stored_choices(self, grant_ids: Iterable[int]) -> dict[int, list[CharacterFeatureChoice]]:
        """Stored picks of the given grants, grouped by grant id."""

        ids = list(grant_ids)
        stored: dict[int, list[CharacterFeatureChoice]] = {grant_id: [] for grant_id in ids}
        for choice in await self.grant_repository.get_choices(ids):
            stored[choice.character_feature_id].append(choice)
        return stored

    async def get_pending_choice_groups(
        self, character_id: int, grant_id: int, current_user: UserResponse
    ) -> PendingChoiceGroupsResponse:
        """Return the grant's choice groups that still need the player's picks."""

        await self.ensure_character_access(character_id, current_user)

        grant = await self._load_grant(character_id, grant_id)
        feature = (await self._load_trees([grant], only_with_choices=False)).get(grant.feature_id)
        if feature is None:
            raise GrantNotFoundError(character_id=character_id, grant_id=grant_id)

        stored = (await self._load_stored_choices([grant.id]))[grant.id]
        return await self._pending_response(grant, feature, stored)

    async def _pending_response(
        self,
        grant: CharacterFeature,
        feature: Feature,
        stored: list[CharacterFeatureChoice],
        context: "_RulesContext | None" = None,
    ) -> PendingChoiceGroupsResponse:
        """
        The grant's pending groups; SKILL groups are judged against the grant's baseline and open spell
        options against the spells the character has, both without the grant's picks in the pending groups.
        ``context`` shares the character's sources across several grants (and the checks of a write).
        """

        pending = pending_groups(feature, stored)
        has_skills, has_open_spells = _has_skill_group(pending), _has_open_spell_option(pending)
        if not (has_skills or has_open_spells):
            return _to_pending_response(grant, feature, pending)

        context = context or self._context(grant.character_id)
        own = _own_effects(feature, stored, {group.id for group in pending})

        baseline, all_skill_ids = None, None
        if has_skills:
            baseline = (await context.skill_sources()).baseline(grant.id, feature, own)
            all_skill_ids = await context.all_skill_ids()

        candidates, ownership = None, None
        if has_open_spells:
            candidates = await context.spell_candidates()
            ownership = (await context.spell_sources()).ownership(grant.id, own.spells)

        return _to_pending_response(grant, feature, pending, baseline, all_skill_ids, candidates, ownership)

    async def get_all_pending_choices(
        self, character_id: int, current_user: UserResponse
    ) -> list[PendingChoiceGroupsResponse]:
        """
        Scan every feature/feat grant on the character and return only the
        ones that still have unanswered choice groups — the character-wide
        "you still need to choose" surface, meant to drive a forced picker
        right after character creation or a level-up.

        Only grants of features with choice groups (``Feature.has_choices``)
        are loaded; their trees and stored picks come in one batch each.
        """

        await self.ensure_character_access(character_id, current_user)

        grants = await self.grant_repository.get_grants_with_choices(character_id)
        if not grants:
            return []

        features = await load_feature_effect_trees(
            self.db, {grant.feature_id for grant in grants}, with_spell_filters=True
        )
        stored_by_grant = await self._load_stored_choices(grant.id for grant in grants)
        context = self._context(character_id)

        responses = []
        for grant in grants:
            feature = features.get(grant.feature_id)
            if feature is None:
                continue

            stored = stored_by_grant[grant.id]
            if pending_groups(feature, stored):
                responses.append(await self._pending_response(grant, feature, stored, context))

        return responses

    async def count_pending_choices(self, character_id: int, current_user: UserResponse) -> PendingChoicesCountResponse:
        """
        How many grants still have unanswered choice groups — the light badge read: no skill/spell sources,
        no candidate lists, just the trees' groups against the stored picks.
        """

        await self.ensure_character_access(character_id, current_user)

        grants = await self.grant_repository.get_grants_with_choices(character_id)
        if not grants:
            return PendingChoicesCountResponse(count=0)

        features = await load_feature_effect_trees(self.db, {grant.feature_id for grant in grants})
        stored_by_grant = await self._load_stored_choices(grant.id for grant in grants)
        count = sum(
            1
            for grant in grants
            if (feature := features.get(grant.feature_id)) is not None
            and pending_groups(feature, stored_by_grant[grant.id])
        )
        return PendingChoicesCountResponse(count=count)

    async def get_answered_choices(
        self, character_id: int, grant_id: int, current_user: UserResponse
    ) -> AnsweredChoicesResponse:
        """
        Return the player's resolved picks for one grant's choice groups —
        the options actually chosen, with their full effect bundle. An empty
        ``choices`` list means nothing has been answered yet (see
        ``get_pending_choice_groups`` for what's still outstanding).
        """

        await self.ensure_character_access(character_id, current_user)

        grant = await self._load_grant(character_id, grant_id, with_answers=True)
        return _to_answered_response(grant)

    async def get_all_answered_choices(
        self, character_id: int, current_user: UserResponse
    ) -> list[AnsweredChoicesResponse]:
        """
        Character-wide view of every grant that has at least one answered
        choice group, with the options picked — the answered-side mirror of
        ``get_all_pending_choices``.
        """

        await self.ensure_character_access(character_id, current_user)

        grants = await self.grant_repository.get_answered_grants(character_id)
        return [_to_answered_response(grant) for grant in grants]

    async def _store_answers(
        self,
        grant: CharacterFeature,
        feature: Feature,
        stored: list[CharacterFeatureChoice],
        answers: list[ChoiceAnswerItem],
        context: "_RulesContext | None" = None,
    ) -> list[CharacterFeatureChoice]:
        """
        Validate ``answers`` and replace each answered group's stored picks
        (flush only). Returns the grant's picks after the replacement.
        ``context`` (a write context, ``flush_first``) may be shared with the
        response built right after; without one a fresh one is made, so picks
        written for an earlier grant of the same transaction count.

        Skill picks are judged against the character's other sources (see
        ``grants.skill_rules``): named skills must exist, and each picked
        SKILL option must fit — in the feature's group order, every accepted
        pick counting for the next. Spells named for open spell options are
        judged the same way by ``grants.spell_rules``.
        """

        answered = _validate_answers(grant.id, feature, answers)
        if not answered:
            return stored

        context = context or self._context(grant.character_id, flush_first=True)
        await self._check_skill_picks(grant, feature, stored, answered, context)
        await self._check_spell_picks(grant, feature, stored, answered, context)

        new_choices = await self.grant_repository.replace_choices(
            grant.id,
            {
                group_id: [(pick.option.id, pick.skill_id, pick.spell_id, pick.ability) for pick in picks]
                for group_id, picks in answered.items()
            },
        )
        return [choice for choice in stored if choice.choice_group_id not in answered] + new_choices

    async def _check_skill_picks(
        self,
        grant: CharacterFeature,
        feature: Feature,
        stored: list[CharacterFeatureChoice],
        answered: dict[int, list[OptionPick]],
        context: "_RulesContext",
    ) -> None:
        """Raise when a named skill doesn't exist or a picked SKILL option doesn't fit the character."""

        named = {pick.skill_id for picks in answered.values() for pick in picks if pick.skill_id is not None}
        missing = await self.rules_repository.missing_skill_ids(named)
        if missing:
            raise UnknownSkillPickError(skill_ids=missing)

        skill_groups = [
            group for group in feature.choice_groups if group.id in answered and group.choice_type == ChoiceType.SKILL
        ]
        if not skill_groups:
            return

        sources = await context.skill_sources()
        baseline = sources.baseline(grant.id, feature, _own_effects(feature, stored, set(answered)))
        for group in skill_groups:
            for pick in answered[group.id]:
                refusal = option_refusal(pick.option, pick.skill_id, baseline)
                if refusal is not None:
                    refused_skill_id, reason = refusal
                    raise SkillPickNotAllowedError(option_id=pick.option.id, skill_id=refused_skill_id, reason=reason)
                apply_option(pick.option, pick.skill_id, baseline)

    async def _check_spell_picks(
        self,
        grant: CharacterFeature,
        feature: Feature,
        stored: list[CharacterFeatureChoice],
        answered: dict[int, list[OptionPick]],
        context: "_RulesContext",
    ) -> None:
        """Raise when a named spell doesn't exist or doesn't fit its open option (filter, already owned)."""

        named = {pick.spell_id for picks in answered.values() for pick in picks if pick.spell_id is not None}
        if not named:
            return

        facts = await self.rules_repository.spell_facts(named)
        missing = sorted(named - set(facts))
        if missing:
            raise UnknownSpellPickError(spell_ids=missing)

        sources = await context.spell_sources()
        ownership = sources.ownership(grant.id, _own_effects(feature, stored, set(answered)).spells)
        for group in feature.choice_groups:
            for pick in answered.get(group.id, []):
                effect = open_spell_effect(pick.option)
                if effect is None or pick.spell_id is None:
                    continue

                reason = spell_refusal(effect, facts[pick.spell_id], ownership)
                if reason is not None:
                    raise SpellPickNotAllowedError(option_id=pick.option.id, spell_id=pick.spell_id, reason=reason)
                ownership.owned.add(pick.spell_id)

    async def resolve_grants_choices(
        self,
        grants: list[CharacterFeature],
        answers_by_feature: dict[int, list[ChoiceAnswerItem]],
        *,
        enforce: bool = True,
    ) -> None:
        """
        Apply ``answers_by_feature`` (keyed by feature id) to the choice
        groups of ``grants``, loading every effect tree and every grant's
        stored picks in one batch each; grants of features without choice
        groups are skipped without loading.

        With ``enforce=True`` (the strict default) raises
        ``GrantChoiceRequiredException`` if a group is still unresolved
        afterward, aborting the caller's whole write.

        With ``enforce=False`` (level-up, GM-panel grants) given answers are
        still applied, but a still-pending group is left pending — the grant
        lands first and gets its choice picked later via ``PATCH
        /features/{id}/choices``; ``get_all_pending_choices`` is the surface
        a client polls to know a grant still needs one.

        Flush only; never refreshes stats / invalidates the cache.
        """

        features = await self._load_trees(grants, only_with_choices=True)
        grants_with_choices = [grant for grant in grants if grant.feature_id in features]
        stored_by_grant = await self._load_stored_choices(grant.id for grant in grants_with_choices)

        for grant in grants_with_choices:
            feature = features[grant.feature_id]
            stored = stored_by_grant[grant.id]

            answers = answers_by_feature.get(grant.feature_id, [])
            if answers:
                stored = await self._store_answers(grant, feature, stored, answers)

            still_pending = pending_groups(feature, stored)
            if still_pending and enforce:
                raise GrantChoiceRequiredException(
                    feature_id=feature.id,
                    feature_name=feature.name,
                    pending_group_ids=[group.id for group in still_pending],
                )

    async def resolve_grant_choices(
        self,
        character: Character,
        grant: CharacterFeature,
        answers: list[ChoiceAnswerItem],
        *,
        enforce: bool = True,
    ) -> None:
        """Single-grant :meth:`resolve_grants_choices` (``character`` is unused: the grant is already scoped to it)."""

        await self.resolve_grants_choices([grant], {grant.feature_id: answers}, enforce=enforce)

    async def answer_choices(
        self,
        character_id: int,
        grant_id: int,
        data: GrantChoicesUpdate,
        current_user: UserResponse,
    ) -> PendingChoiceGroupsResponse:
        """
        Answer the grant's pending choice groups (full replace per group).

        Validates the request against the feature's groups/options and
        replaces each answered group's stored picks in one transaction owned
        here (grant row locked against a concurrent re-answer). An
        ability-score pick may not take the score above 20 (the player's
        structured choices are capped there — a feat's ASI pick included,
        since a level-up only takes the feat). The picks' effects show up on
        the next read; only the ability-score cache is refreshed in the
        transaction and the character's Redis payload is purged after the
        commit.
        """

        character = await self.get_character_for_user(character_id, current_user)

        async with self._atomic():
            grant = await self._load_grant(character_id, grant_id, for_update=True)
            feature = (await self._load_trees([grant], only_with_choices=False)).get(grant.feature_id)
            if feature is None:
                raise GrantNotFoundError(character_id=character_id, grant_id=grant_id)

            stored = (await self._load_stored_choices([grant.id]))[grant.id]
            # one context for the checks and the response: both judge the grant without its own picks,
            # and no other grant changes in this request
            context = self._context(character_id, flush_first=True)
            stored = await self._store_answers(grant, feature, stored, data.answers, context)

            totals = await self.stats_service.compute(character)
            _ensure_picks_within_cap(feature, data.answers, totals)
            await self.stats_service.store(character, totals)
            await self._invalidate_character(character_id)

            return await self._pending_response(grant, feature, stored, context)


def _ensure_picks_within_cap(feature: Feature, answers: list[ChoiceAnswerItem], totals: dict[str, int]) -> None:
    """
    Raise ``AbilityPickCapExceededError`` when a picked ability-score option raises a score that ends up
    above ``ABILITY_SCORE_CAP`` (or the option's own ``new_cap``) — ``totals`` already include the picks.
    """

    options = {
        option.id: option
        for group in feature.choice_groups
        if group.choice_type == ChoiceType.ABILITY_SCORE
        for option in group.options
    }
    for item in answers:
        option = options.get(item.choice_option_id)
        if option is None:
            continue
        for effect in option.ability_effects:
            ability = effect.ability if effect.ability is not None else item.ability
            if ability is None:
                continue
            total = totals[TOTAL_FIELD_BY_ABILITY[ability]]
            cap = max(ABILITY_SCORE_CAP, effect.new_cap or 0)
            if effect.amount > 0 and total > cap:
                raise AbilityPickCapExceededError(
                    ability=ability.value,
                    current_total=total - effect.amount,
                    requested=total,
                    cap=cap,
                )


class _RulesContext:
    """
    What the pick rules judge against, loaded lazily and once per request: every grant's computed effects
    (shared by the skill and the spell sources), the stored proficiency rows, every skill id and every catalog
    spell. ``flush_first`` (write paths) flushes before the first load, so picks written earlier in the
    transaction count; a read never flushes.
    """

    def __init__(self, service: FeatureGrantService, character_id: int, *, flush_first: bool = False):
        self.service = service
        self.character_id = character_id
        self.flush_first = flush_first
        self._grants: dict[int, tuple[Feature, GrantEffects]] | None = None
        self._skill_sources: SkillSources | None = None
        self._all_skill_ids: list[int] | None = None
        self._spell_sources: SpellSources | None = None
        self._spell_candidates: list[SpellFacts] | None = None

    async def _grant_effects(self) -> dict[int, tuple[Feature, GrantEffects]]:
        if self._grants is None:
            if self.flush_first:
                await self.service.db.flush()
            self._grants = await load_character_grant_effects_by_grant(self.service.db, self.character_id)
        return self._grants

    async def skill_sources(self) -> SkillSources:
        if self._skill_sources is None:
            grants = await self._grant_effects()
            rows = await self.service.proficiency_repository.get_all(self.character_id)
            self._skill_sources = build_skill_sources(rows, grants)
        return self._skill_sources

    async def all_skill_ids(self) -> list[int]:
        if self._all_skill_ids is None:
            self._all_skill_ids = await self.service.rules_repository.all_skill_ids()
        return self._all_skill_ids

    async def spell_sources(self) -> SpellSources:
        if self._spell_sources is None:
            grants = await self._grant_effects()
            repository = self.service.rules_repository
            self._spell_sources = build_spell_sources(
                await repository.castable_spell_levels(self.character_id),
                await repository.row_spell_ids(self.character_id),
                grants,
            )
        return self._spell_sources

    async def spell_candidates(self) -> list[SpellFacts]:
        if self._spell_candidates is None:
            self._spell_candidates = list((await self.service.rules_repository.spell_facts()).values())
        return self._spell_candidates
