"""Character crud service: CRUD, HP management, and resting."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType, UserRole
from app.core.base.service import BaseService, Page, paginate
from app.core.cache import use_cache
from app.core.cache.client import cache_prefix
from app.core.exceptions import GmAccessException
from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.characters.ability_score.calculator import BASE_FIELD_BY_ABILITY, DerivedStats
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.access import get_character_for_user, get_character_or_404
from app.features.characters.cache import CHARACTER_CACHE_NAMESPACE, invalidate_character_cache
from app.features.characters.crud.exceptions import (
    InvalidHpUpdateException,
    ItemChoiceNotAvailableException,
    ItemChoicesWithoutGroupsException,
    SkillNotAvailableForClassException,
    TooFewItemChoicesException,
    TooManySkillChoicesException,
)
from app.features.characters.crud.repository import CharacterRepository
from app.features.characters.crud.schemas import HpUpdate, RestRequest
from app.features.characters.exceptions import BackgroundNotFoundException
from app.features.characters.feats.repository import CharacterFeatRepository
from app.features.characters.features.repository import CharacterFeatureRepository
from app.features.characters.items.repository import CharacterItemRepository
from app.features.characters.level.repository import CharacterMaxLevelRepository
from app.features.characters.progression.feature_sync import sync_progression_features
from app.features.characters.progression.repository import CharacterASIChoiceRepository
from app.features.characters.schemas import (
    AbilityScoresResponse,
    AbilityStatsView,
    CharacterCreate,
    CharacterFeatResponse,
    CharacterFeatureResponse,
    CharacterItemResponse,
    CharacterResponse,
    CharacterStatsResponse,
    CharacterUpdate,
    SavingThrowProficiencyResponse,
)
from app.features.characters.spells.repository import CharacterSpellSlotRepository
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.exceptions import ClassNotFoundException, SubclassNotFoundException
from app.features.items.crud.repository import ItemRepository
from app.features.races.crud.repository import RaceRepository
from app.features.races.exceptions import RaceNotFoundException, SubraceNotFoundException
from app.features.users.schemas import UserResponse
from app.models import CharacterAbilityScore, CharacterSkillProficiency, Class
from app.models.character_backstory_model import CharacterBackstory
from app.models.character_item_model import CharacterItem
from app.models.character_model import Character
from app.models.source_item_choice_model import SourceItemChoiceOption


class CharacterService(BaseService[Character, CharacterCreate, CharacterUpdate, CharacterResponse]):
    """
    Core character CRUD, HP management, and resting. Owns the character
    record plus its FK/skill/HP creation contract and the ability-score
    cache write policy (reads never recompute); spell slots are applied on
    create and re-applied by the progression service on level-up/class change.
    """

    repository: CharacterRepository

    def __init__(self, db: AsyncSession):
        """Set up the character service and its collaborators."""

        super().__init__(
            repository=CharacterRepository(db),
            response_schema=CharacterResponse,
        )
        self.character_spell_slot_repository = CharacterSpellSlotRepository(db)
        self.class_repository = ClassRepository(db)
        self.race_repository = RaceRepository(db)
        self.background_repository = BackgroundRepository(db)
        self.item_repository = ItemRepository(db)
        self.feat_grant_repository = CharacterFeatRepository(db)
        self.feature_grant_repository = CharacterFeatureRepository(db)
        self.character_item_repository = CharacterItemRepository(db)
        self.max_level_repository = CharacterMaxLevelRepository(db)
        self.asi_repository = CharacterASIChoiceRepository(db)
        self.stats_service = CharacterStatsService(db)

    async def get_characters(
        self,
        current_user: UserResponse,
        *,
        search: str | None = None,
        class_id: int | None = None,
        page: int = 1,
        size: int = 100,
    ) -> Page[CharacterResponse]:
        """
        Return every character for a GM, or only the caller's own for a
        player, as a paginated ``Page`` envelope. Ability scores reflect
        the cache; ``search``/``class_id`` optionally filter.
        """

        owner_id = None if current_user.role in (UserRole.GM, UserRole.FOUND_FATHER) else current_user.id
        return await self._list_characters(owner_id=owner_id, search=search, class_id=class_id, page=page, size=size)

    async def get_my_characters(
        self,
        current_user: UserResponse,
        *,
        search: str | None = None,
        class_id: int | None = None,
        page: int = 1,
        size: int = 100,
    ) -> Page[CharacterResponse]:
        """
        Return only the characters owned by the caller — for every role,
        including GMs.
        """

        return await self._list_characters(
            owner_id=current_user.id, search=search, class_id=class_id, page=page, size=size
        )

    async def get_all_characters(
        self,
        current_user: UserResponse,
        *,
        search: str | None = None,
        class_id: int | None = None,
        page: int = 1,
        size: int = 100,
    ) -> Page[CharacterResponse]:
        """Return every user's characters. GM-only — anyone else gets a 403."""

        if current_user.role not in (UserRole.GM, UserRole.FOUND_FATHER):
            raise GmAccessException()

        return await self._list_characters(owner_id=None, search=search, class_id=class_id, page=page, size=size)

    async def _list_characters(
        self,
        *,
        owner_id: int | None,
        search: str | None,
        class_id: int | None,
        page: int,
        size: int,
    ) -> Page[CharacterResponse]:
        """Shared paginated listing behind all three list endpoints."""

        filters: dict[str, Any] = {}
        if owner_id is not None:
            filters["owner_id"] = owner_id

        if class_id is not None:
            filters["class_id"] = class_id

        filters = filters or None

        skip, limit = paginate(page, size)
        characters = await self.repository.get_all(
            filters=filters,
            search=search,
            order_by=Character.name,
            skip=skip,
            limit=limit,
        )
        total = await self.repository.count(filters=filters, search=search)

        cache_by_id = await self.stats_service.get_many_or_stale([character.id for character in characters])
        derived_by_id = await self.stats_service.get_many_derived(characters)
        return Page(
            items=[
                await self._to_response(
                    character, cache_row=cache_by_id.get(character.id), derived=derived_by_id.get(character.id)
                )
                for character in characters
            ],
            total=total,
            page=page,
            size=size,
        )

    async def get_character(self, character_id: int, current_user: UserResponse) -> CharacterResponse:
        """
        Return a single character, enforcing GM/owner access. The response
        assembly is cached per character_id so repeated reads skip the DB
        round-trips (access control is never cached).
        """

        await get_character_for_user(self.repository, character_id, current_user)
        return await self._get_character_response(character_id)

    async def get_feats(self, character_id: int, current_user: UserResponse) -> list[CharacterFeatResponse]:
        """List every feat granted to a character (level-up choices and GM grants alike)."""

        await get_character_for_user(self.repository, character_id, current_user)

        grants = await self.feat_grant_repository.get_character_feats(character_id)
        return [CharacterFeatResponse.model_validate(grant) for grant in grants]

    async def get_stats(self, character_id: int, current_user: UserResponse) -> CharacterStatsResponse:
        """
        Return each ability's ORIGINAL base value next to its COMPUTED
        effective total, with the source contributions that produced it.
        """

        character = await get_character_for_user(self.repository, character_id, current_user)
        breakdown_by_ability = await self.stats_service.compute_breakdown(character)

        return CharacterStatsResponse(
            **{
                BASE_FIELD_BY_ABILITY[ability]: AbilityStatsView(
                    base=breakdown.base,
                    total=breakdown.total,
                    contributions=[
                        {"source": c.source, "label": c.label, "amount": c.amount} for c in breakdown.contributions
                    ],
                )
                for ability, breakdown in breakdown_by_ability.items()
            }
        )

    async def get_features(self, character_id: int, current_user: UserResponse) -> list[CharacterFeatureResponse]:
        """List every feature recorded on a character (progression auto-grants plus GM records)."""

        await get_character_for_user(self.repository, character_id, current_user)

        grants = await self.feature_grant_repository.get_character_features(character_id)
        return [CharacterFeatureResponse.model_validate(grant) for grant in grants]

    async def get_items(self, character_id: int, current_user: UserResponse) -> list[CharacterItemResponse]:
        """List every item stack a character owns (GM/owner readable)."""

        await get_character_for_user(self.repository, character_id, current_user)

        stacks = await self.character_item_repository.get_character_items(character_id)
        return [CharacterItemResponse.model_validate(stack) for stack in stacks]

    @use_cache(
        key_builder=lambda self, character_id, **_: f"{cache_prefix()}:{CHARACTER_CACHE_NAMESPACE}:{character_id}",
    )
    async def _get_character_response(self, character_id: int) -> CharacterResponse:
        """Cached response assembly for a single character (access check is NOT cached)."""

        character = await get_character_or_404(self.repository, character_id)
        return await self._to_response(character, refresh=False)

    async def create_character(self, character_data: CharacterCreate, current_user: UserResponse) -> CharacterResponse:
        """
        One-shot creation of a level-1 character owned by the caller.

        Validates the FK references (class required, subclass/race/subrace/
        background must belong and exist), the skill choices against the
        class + background + race grants, and the starting-equipment "pick
        N of M" choices. Character row, proficiencies, slot rows, feature
        grants (via ``sync_progression_features``), backstory, and starting
        items are written in one transaction.
        """

        await self._validate_references(
            class_id=character_data.class_id,
            subclass_id=character_data.subclass_id,
            race_id=character_data.race_id,
            subrace_id=character_data.subrace_id,
            background_id=character_data.background_id,
        )

        # Fetched once so the flow can rely on the eager-loaded
        # available_skills / saving_throws / hit dice.
        character_class = await self.class_repository.get_by_id(character_data.class_id)
        if character_class is None:
            raise ClassNotFoundException(class_id=character_data.class_id)

        chosen_skill_ids = self._validate_chosen_skills(character_data.skill_ids, character_class)

        chosen_item_options = await self._resolve_item_choices(
            character_data.class_id, character_data.background_id, character_data.item_choice_ids
        )

        background_skill_ids: list[int] = []
        background_personality = {
            "personality_traits": "",
            "ideals": "",
            "bonds": "",
            "flaws": "",
        }
        background_description = ""
        if character_data.background_id is not None:
            background = await self.background_repository.get_by_id(character_data.background_id)
            if background is not None:
                background_skill_ids = [skill.id for skill in background.granted_skills]
                # Always take the personality card from the background when one
                # is chosen (the player's own values are replaced with the
                # background's suggestions).
                background_personality = {
                    "personality_traits": background.personality_traits_suggestions,
                    "ideals": background.ideals_suggestions,
                    "bonds": background.bonds_suggestions,
                    "flaws": background.flaws_suggestions,
                }
                # The backstory is written from the background's description —
                # the client does not send backstory at creation.
                background_description = background.description

        # Same pattern as the background: get_by_id eager-loads granted_skills,
        # so no extra query is needed to collect them.
        race_skill_ids: list[int] = []
        if character_data.race_id is not None:
            race = await self.race_repository.get_by_id(character_data.race_id)
            if race is not None:
                race_skill_ids = [skill.id for skill in race.granted_skills]

        payload = character_data.model_dump(exclude={"skill_ids", "item_choice_ids"})
        payload["owner_id"] = current_user.id
        payload["level"] = 1
        payload["temp_hp"] = 0
        if character_data.background_id is not None:
            payload.update(background_personality)

        async with self._atomic():
            character = await self.repository.create(payload, commit=False)

            # The backstory description is kept off the cached character, on
            # its own dedicated row, mirroring the backstory endpoints. It is
            # written from the background's description when a background is
            # chosen at creation.
            if background_description:
                self.repository.db.add(CharacterBackstory(character_id=character.id, content=background_description))

            # The GM-set level-up cap starts at the character's starting
            # level: it cannot level up until a GM raises its maximum.
            await self.max_level_repository.create_for_character(character.id, character.level, commit=False)

            await self._apply_skill_proficiencies(
                character, chosen_skill_ids, background_skill_ids, race_skill_ids, commit=False
            )
            await self._apply_spell_slot_progression(character, commit=False)

            # Features are granted BEFORE the starting-HP math so their
            # fixed ability effects (e.g. +4 CON) are included in the
            # effective CON modifier from the very first hit point.
            await sync_progression_features(self.repository.db, character)
            # The session runs with autoflush=False — flush the pending
            # grant rows so the stats computation below can read them.
            await self.repository.db.flush()

            max_hp = await self._compute_starting_max_hp(character, character_class)
            character.max_hp = max_hp
            character.current_hp = max_hp
            await self.repository.db.flush()

            await self._apply_starting_equipment(character, chosen_item_options, commit=False)

        character = await get_character_for_user(self.repository, character.id, current_user)
        await invalidate_character_cache(character.id)

        return await self._to_response(character, refresh=True)

    @staticmethod
    def _validate_chosen_skills(skill_ids: list[int], character_class: Class) -> list[int]:
        """
        Validate the player's class skill choices: every id must be one of
        the class's ``available_skills`` and the total must not exceed
        ``skill_choice_count``.
        """

        if not skill_ids:
            return []

        allowed = character_class.skill_choice_count
        if len(skill_ids) > allowed:
            raise TooManySkillChoicesException(class_id=character_class.id, allowed=allowed, requested=len(skill_ids))

        available_ids = {skill.id for skill in character_class.available_skills}
        for skill_id in skill_ids:
            if skill_id not in available_ids:
                raise SkillNotAvailableForClassException(class_id=character_class.id, skill_id=skill_id)

        return skill_ids

    async def _resolve_item_choices(
        self,
        class_id: int | None,
        background_id: int | None,
        item_choice_ids: list[int],
    ) -> list[SourceItemChoiceOption]:
        """
        Resolve the player's starting-equipment "pick N of M" choices
        against the choice groups of the character's class/background: every
        group must be answered with exactly ``pick_count`` options.
        """

        sources: list[tuple[FeatureSourceType, int]] = []
        if class_id is not None:
            sources.append((FeatureSourceType.CLASS, class_id))
        if background_id is not None:
            sources.append((FeatureSourceType.BACKGROUND, background_id))

        if not sources:
            if item_choice_ids:
                raise ItemChoicesWithoutGroupsException()
            return []

        groups = await self.item_repository.get_choice_groups_for_sources(sources)

        if not groups:
            if item_choice_ids:
                raise ItemChoicesWithoutGroupsException()
            return []

        option_by_id: dict[int, SourceItemChoiceOption] = {}
        for group in groups:
            for option in group.options:
                option_by_id[option.id] = option

        chosen_options: list[SourceItemChoiceOption] = []
        for option_id in item_choice_ids:
            option = option_by_id.get(option_id)
            if option is None:
                raise ItemChoiceNotAvailableException(option_id=option_id)
            chosen_options.append(option)

        choices_by_group: dict[int, int] = {}
        for option in chosen_options:
            choices_by_group[option.group_id] = choices_by_group.get(option.group_id, 0) + 1

        for group in groups:
            chosen = choices_by_group.get(group.id, 0)
            if chosen != group.pick_count:
                raise TooFewItemChoicesException(group_id=group.id, pick_count=group.pick_count, chosen=chosen)

        return chosen_options

    async def _compute_starting_max_hp(self, character: Character, character_class: Class) -> int:
        """
        Starting max HP for a level-1 character: the full hit die + the
        *effective* CON modifier, clamped to a minimum of 1.
        """

        die_faces = int(character_class.hit_dice.value[1:])
        totals = await self.stats_service.compute(character)
        con_mod = (totals["constitution_total"] - 10) // 2

        return max(die_faces + con_mod, 1)

    async def _apply_skill_proficiencies(
        self,
        character: Character,
        chosen_skill_ids: list[int],
        background_skill_ids: list[int],
        race_skill_ids: list[int],
        *,
        commit: bool = True,
    ) -> None:
        """
        Write the starting skill proficiencies: the validated class choices
        plus the background's and race's granted skills, deduplicated, all
        starting with ``is_expertise=False``.
        """

        merged_skill_ids = list(dict.fromkeys([*chosen_skill_ids, *background_skill_ids, *race_skill_ids]))
        for skill_id in merged_skill_ids:
            self.repository.db.add(
                CharacterSkillProficiency(character_id=character.id, skill_id=skill_id, is_expertise=False)
            )

        if commit:
            await self.repository.db.commit()
        else:
            await self.repository.db.flush()

    async def update_character(
        self, character_id: int, update_data: CharacterUpdate, current_user: UserResponse
    ) -> CharacterResponse:
        """
        Partially update a character, enforcing GM/owner access. Only fields
        present in ``CharacterUpdate`` are changeable — class/background,
        level, and base ability scores cannot be changed here.
        """

        character = await get_character_for_user(self.repository, character_id, current_user)

        fields = update_data.model_dump(exclude_unset=True)
        updated_character = await self.repository.update(character, fields)

        await invalidate_character_cache(character_id)
        return await self._to_response(updated_character, refresh=False)

    async def delete_character(self, character_id: int, current_user: UserResponse) -> bool:
        """Delete a character, enforcing GM/owner access."""

        character = await get_character_for_user(self.repository, character_id, current_user)
        return await self.repository.delete(character)

    async def update_hp(self, character_id: int, data: HpUpdate, current_user: UserResponse) -> CharacterResponse:
        """
        Update HP either via a relative delta, or by setting absolute values.

        Deltas follow 5e rules: damage drains ``temp_hp`` first (overflow
        hits ``current_hp``); healing restores ``current_hp`` only. An
        absolute ``temp_hp`` is a gain that applies only when higher than
        the current pool (temp HP never stacks). ``current_hp`` is clamped
        to ``[0, max_hp]``; ``temp_hp`` to ``>= 0``. Mixing delta and
        absolute values is rejected.
        """

        character = await get_character_for_user(self.repository, character_id, current_user)

        has_delta = data.delta is not None
        has_absolute = data.current_hp is not None or data.temp_hp is not None
        if has_delta and has_absolute:
            raise InvalidHpUpdateException()
        if not has_delta and not has_absolute:
            raise InvalidHpUpdateException("Provide either 'delta' or an absolute HP value.")

        if has_delta:
            new_current_hp, new_temp_hp = self._apply_hp_delta(character.current_hp, character.temp_hp, data.delta)
        else:
            new_current_hp = data.current_hp if data.current_hp is not None else character.current_hp
            gained_temp = data.temp_hp if data.temp_hp is not None else character.temp_hp
            new_temp_hp = max(character.temp_hp, gained_temp)

        new_current_hp = max(0, min(new_current_hp, character.max_hp))
        new_temp_hp = max(0, new_temp_hp)

        updated_character = await self.repository.update_hp(character, new_current_hp, new_temp_hp)
        await invalidate_character_cache(character_id)
        return await self._to_response(updated_character, refresh=False)

    @staticmethod
    def _apply_hp_delta(current_hp: int, temp_hp: int, delta: int) -> tuple[int, int]:
        """
        Resolve a healing/damage delta per 5e rules: healing adds to
        ``current_hp`` only; damage drains ``temp_hp`` first with overflow
        hitting ``current_hp``. Returns unclamped values for the caller.
        """

        if delta >= 0:
            return current_hp + delta, temp_hp

        damage = -delta
        absorbed = min(temp_hp, damage)
        return current_hp - (damage - absorbed), temp_hp - absorbed

    async def rest(self, character_id: int, data: RestRequest, current_user: UserResponse) -> CharacterResponse:
        """
        Apply a short or long rest. Long rest restores HP to max and clears
        temp HP; short rest is a no-op placeholder until hit dice are tracked.
        """

        character = await get_character_for_user(self.repository, character_id, current_user)

        if data.type == "long":
            await self.repository.update_hp(character, character.max_hp, 0)
            await self.character_spell_slot_repository.reset_all_spell_slots(character_id)
            character = await get_character_or_404(self.repository, character_id)

        await invalidate_character_cache(character_id)
        return await self._to_response(character, refresh=False)

    async def _validate_references(
        self,
        *,
        class_id: int,
        subclass_id: int | None,
        race_id: int | None,
        subrace_id: int | None,
        background_id: int | None,
    ) -> None:
        """
        Raise the matching not-found exception if any given ID doesn't
        exist. Called from :meth:`create_character` only.
        """

        if not await self.class_repository.exists_by_id(class_id):
            raise ClassNotFoundException(class_id=class_id)

        if subclass_id is not None and await self.class_repository.get_subclass(class_id, subclass_id) is None:
            raise SubclassNotFoundException(class_id=class_id, subclass_id=subclass_id)

        if race_id is not None and not await self.race_repository.exists_by_id(race_id):
            raise RaceNotFoundException(race_id=race_id)

        if subrace_id is not None:
            if race_id is None:
                raise SubraceNotFoundException(race_id=race_id or 0, subrace_id=subrace_id)

            if await self.race_repository.get_subrace(race_id, subrace_id) is None:
                raise SubraceNotFoundException(race_id=race_id, subrace_id=subrace_id)

        if background_id is not None and not await self.background_repository.exists_by_id(background_id):
            raise BackgroundNotFoundException(background_id=background_id)

    async def _apply_spell_slot_progression(self, character: Character, *, commit: bool = True) -> None:
        """
        Sync ``CharacterSpellSlot`` totals to the class's spell slot
        progression for the character's current level.
        """

        slots_by_level = (
            await self.class_repository.get_spell_slot_progression(character.class_id, character.level)
            if character.class_id is not None
            else {}
        )
        await self.character_spell_slot_repository.apply_spell_slot_progression(
            character.id, slots_by_level, commit=commit
        )

    async def _apply_starting_equipment(
        self,
        character: Character,
        chosen_options: list[SourceItemChoiceOption],
        *,
        commit: bool = True,
    ) -> None:
        """
        Grant the character the starting equipment of its class and
        background: one ``CharacterItem`` stack per item with quantities
        summed across sources and the resolved "pick N of M" choices.
        """

        sources: list[tuple[FeatureSourceType, int]] = []
        if character.class_id is not None:
            sources.append((FeatureSourceType.CLASS, character.class_id))
        if character.background_id is not None:
            sources.append((FeatureSourceType.BACKGROUND, character.background_id))

        if not sources:
            return

        entries = await self.item_repository.get_source_items_for_sources(sources)

        quantities: dict[int, int] = {}
        for entry in entries:
            quantities[entry.item_id] = quantities.get(entry.item_id, 0) + entry.quantity
        for option in chosen_options:
            quantities[option.item_id] = quantities.get(option.item_id, 0) + option.quantity

        for item_id, quantity in quantities.items():
            self.repository.db.add(CharacterItem(character_id=character.id, item_id=item_id, quantity=quantity))

        if commit:
            await self.repository.db.commit()
        else:
            await self.repository.db.flush()

    async def reapply_spell_slot_progression(self, character: Character, *, commit: bool = True) -> None:
        """Public wrapper around :meth:`_apply_spell_slot_progression` for the progression service."""

        await self._apply_spell_slot_progression(character, commit=commit)

    async def _to_response(
        self,
        character: Character,
        *,
        refresh: bool = False,
        cache_row: CharacterAbilityScore | None = None,
        derived: DerivedStats | None = None,
    ) -> CharacterResponse:
        """
        Serialize a character to ``CharacterResponse``, attaching the
        ability-score cache row (or a fresh one when ``refresh``), the
        derived combat stats, and the class-derived saving throws (the
        class owns them; there is no per-character storage).
        """

        if cache_row is None:
            cache_row = await self.stats_service.for_response(character, refresh=refresh)

        if derived is None:
            derived = await self.stats_service.compute_derived(character)

        response = CharacterResponse.model_validate(character)
        response.ability_scores = AbilityScoresResponse.model_validate(cache_row) if cache_row is not None else None
        response.hit_dice = derived.hit_dice
        response.speed = derived.speed
        response.saving_throw_proficiencies = [
            SavingThrowProficiencyResponse.model_validate(saving_throw)
            for saving_throw in (character.character_class.saving_throws if character.character_class else [])
        ]

        return response
