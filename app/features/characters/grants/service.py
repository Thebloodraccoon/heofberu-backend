"""Character grant service: pending-choice surface and choice answering for the effect engine."""

from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.features.repository import CharacterFeatureRepository
from app.features.characters.grants.effects import (
    build_chosen_options,
    load_feature_effect_trees,
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


def _to_pending_response(
    grant: CharacterFeature, feature: Feature, pending: list[FeatureChoiceGroup]
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
                    # ORM effect rows are validated into the response items by attribute
                    PendingChoiceOption.model_validate(
                        {
                            "id": option.id,
                            "needs_skill": _option_has_open_skill(option),
                            "needs_spell": _option_has_open_spell(option),
                            "effects": effect_groups(option),
                        },
                        from_attributes=True,
                    )
                    for option in group.options
                ],
            )
            for group in pending
        ],
    )


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
) -> dict[int, list[FeatureChoiceOption]]:
    """
    Check ``answers`` against the feature's groups/options and return the
    picked options per group. Raises on a wrong group, an unknown or foreign
    option, a duplicate pick, a wrong pick count, or an option carrying an
    open ("any skill"/"any spell") effect — the system doesn't yet support
    resolving those end to end, so existing catalog data carrying one is
    simply unpickable.
    """

    groups = {group.id: group for group in feature.choice_groups}
    options = {option.id: option for group in feature.choice_groups for option in group.options}
    answered: dict[int, list[FeatureChoiceOption]] = {}

    for item in answers:
        group = groups.get(item.choice_group_id)
        if group is None:
            raise ChoiceGroupNotFoundError(grant_id=grant_id, group_id=item.choice_group_id)

        option = options.get(item.choice_option_id)
        if option is None or option.group_id != group.id:
            raise ChoiceOptionNotFoundError(group_id=group.id, option_id=item.choice_option_id)

        picked = answered.setdefault(group.id, [])
        if any(other.id == option.id for other in picked):
            raise ChoiceOptionAlreadyPickedError(group_id=group.id, option_id=option.id)

        if _option_has_open_skill(option):
            raise SkillResolutionsError(option_id=option.id)

        if _option_has_open_spell(option):
            raise SpellResolutionsError(option_id=option.id)

        picked.append(option)

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
        self.stats_service = CharacterStatsService(db)

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

        return await load_feature_effect_trees(self.db, feature_ids)

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
        return _to_pending_response(grant, feature, pending_groups(feature, stored))

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

        features = await load_feature_effect_trees(self.db, {grant.feature_id for grant in grants})
        stored_by_grant = await self._load_stored_choices(grant.id for grant in grants)

        responses = []
        for grant in grants:
            feature = features.get(grant.feature_id)
            if feature is None:
                continue

            pending = pending_groups(feature, stored_by_grant[grant.id])
            if pending:
                responses.append(_to_pending_response(grant, feature, pending))

        return responses

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
    ) -> list[CharacterFeatureChoice]:
        """
        Validate ``answers`` and replace each answered group's stored picks
        (flush only). Returns the grant's picks after the replacement.
        """

        answered = _validate_answers(grant.id, feature, answers)
        if not answered:
            return stored

        new_choices = await self.grant_repository.replace_choices(
            grant.id, {group_id: [option.id for option in options] for group_id, options in answered.items()}
        )
        return [choice for choice in stored if choice.choice_group_id not in answered] + new_choices

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

        With ``enforce=True`` raises ``GrantChoiceRequiredException`` if a
        group is still unresolved afterward — level-up's newly-unlocked
        features and an ASI-level feat pick both require this: the client
        submits everything in one request, so a still-pending group means the
        request itself was incomplete and the whole write aborts (matches a
        missing ASI ``choice`` being rejected rather than defaulted).

        With ``enforce=False`` (GM-panel grants) given answers are still
        applied, but a still-pending group is left pending — a GM grant may
        land first and get its choice picked later via ``PATCH
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
        here (grant row locked against a concurrent re-answer). The picks'
        effects show up on the next read; only the ability-score cache is
        refreshed in the transaction and the character's Redis payload is
        purged after the commit.
        """

        character = await self.get_character_for_user(character_id, current_user)

        async with self._atomic():
            grant = await self._load_grant(character_id, grant_id, for_update=True)
            feature = (await self._load_trees([grant], only_with_choices=False)).get(grant.feature_id)
            if feature is None:
                raise GrantNotFoundError(character_id=character_id, grant_id=grant_id)

            stored = (await self._load_stored_choices([grant.id]))[grant.id]
            stored = await self._store_answers(grant, feature, stored, data.answers)

            await self.stats_service.refresh(character)
            await self._invalidate_character(character_id)

            return _to_pending_response(grant, feature, pending_groups(feature, stored))
