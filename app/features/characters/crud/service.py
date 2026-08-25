"""Character crud service: CRUD, HP management, and resting."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType, UserRole
from app.core.base.service import BaseService, Page, paginate
from app.core.cache import use_cache
from app.core.cache.client import cache_prefix
from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.characters.ability_score.calculator import DerivedStats
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.access import get_character_for_user, get_character_or_404
from app.features.characters.cache import CHARACTER_CACHE_NAMESPACE, invalidate_character_cache
from app.features.characters.crud.exceptions import (
    InvalidHpUpdateException,
    SkillNotAvailableForClassException,
    TooManySkillChoicesException,
)
from app.features.characters.crud.repository import CharacterRepository
from app.features.characters.crud.schemas import HpUpdate, RestRequest
from app.features.characters.exceptions import BackgroundNotFoundException
from app.features.characters.gm_panel.feats.repository import CharacterFeatRepository
from app.features.characters.gm_panel.features.repository import CharacterFeatureRepository
from app.features.characters.gm_panel.level.repository import CharacterMaxLevelRepository
from app.features.characters.progression.feature_sync import sync_progression_features
from app.features.characters.schemas import (
    AbilityScoresResponse,
    CharacterCreate,
    CharacterFeatResponse,
    CharacterFeatureResponse,
    CharacterResponse,
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
from app.models.character_item_model import CharacterItem
from app.models.character_model import Character


class CharacterService(BaseService[Character, CharacterCreate, CharacterUpdate, CharacterResponse]):
    """
    Core character CRUD, HP management, and resting.

    Built on :class:`BaseService`, mirroring ``RaceCrudService`` /
    ``ClassCrudService`` / ``BackgroundCrudService`` / ``SpellCrudService``:
    ``CharacterRepository`` provides the full generic CRUD (no signature
    overrides), ``owner_id`` is injected into the create payload, and
    ``_get_or_404`` / ``_atomic`` / ``resolve_ids`` come from the base.

    Spell slots, known spells, attacks, and feats each live
    in their own subdomain package; this service owns the character record
    itself plus validating its FK references (class/subclass/race/
    subrace/background) and the one-shot creation contract (level pinned
    to 1, skill choices validated against the class + background grants,
    starting HP resolved from the hit die + CON). Saving throws are not
    stored on the character at all — they are read from the character's
    class on every response. Character progression (race change, class
    change, subclass/subrace change, leveling up) lives in
    ``characters.progression`` and reuses this service for
    serialization and spell-slot re-application.

    Ability score cache policy is decided by
    ``CharacterStatsService`` — this service only tells it *when* a
    write might have touched ability scores. Reads never write:
      - ``get_character`` reads the cache as-is — the cache is kept
        fresh by the write paths themselves, so no read recomputes or
        commits (a plain GET is now fully read-only).
      - ``get_characters`` (listing) likewise returns the cache as-is to
        avoid N recalculations per page.
      - ``create_character`` always refreshes; ``update_character`` never
        refreshes, because ``CharacterUpdate`` holds no ability-affecting
        fields anymore (base scores only change via the level-up ASI, and
        race_id/class_id are not editable here).

    Derived combat stats (hit dice, speed) are computed by
    ``CharacterStatsService`` on every read, for both the detail
    and the listing path. They depend on the class and race, so no
    write path here keeps them in sync — a GM editing a reference
    table is reflected on the next fetch. Armor class is not derived:
    ``armor_class``/``shield`` are plain editable columns (PATCH), set
    directly by the player or GM.

    Spell slot progression policy: applied on create for the starting
    level, and re-applied by the progression service (via
    :meth:`reapply_spell_slot_progression`) whenever a character levels
    up or changes class — a plain PATCH can never touch spell slots.
    """

    repository: CharacterRepository

    def __init__(self, db: AsyncSession):
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
        self.max_level_repository = CharacterMaxLevelRepository(db)
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
        the last-computed cache, not a fresh recalculation — see class
        docstring.

        ``search`` does a case-insensitive substring match against the
        character's ``name`` (pinned via the repository's
        ``search_fields``); ``class_id`` filters to characters of that
        class. Both are optional and combine with the access scoping.
        """

        filters: dict[str, Any] = {}
        if current_user.role != UserRole.GM:
            filters["owner_id"] = current_user.id

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
        Return a single character, enforcing GM/owner access.

        Access control is checked first (never cached). The response
        assembly (ability-score cache read + derived stats + serialization)
        is cached per character_id so repeated reads skip the DB round-trips
        for the response build. The cache key is user-independent — both
        GM and owner see the same CharacterResponse for a given character.
        """

        await get_character_for_user(self.repository, character_id, current_user)
        return await self._get_character_response(character_id)

    async def get_feats(self, character_id: int, current_user: UserResponse) -> list[CharacterFeatResponse]:
        """

        List every feat granted to a character (GM/owner readable).

        Grants come from every source — level-up ASI choices and GM-panel
        grants alike; the writes live in ``gm_panel`` and the progression
        service.
        """

        await get_character_for_user(self.repository, character_id, current_user)

        grants = await self.feat_grant_repository.get_character_feats(character_id)
        return [CharacterFeatResponse.model_validate(grant) for grant in grants]

    async def get_features(self, character_id: int, current_user: UserResponse) -> list[CharacterFeatureResponse]:
        """
        List every feature recorded on a character (GM/owner readable) —
        auto-granted progression features plus GM-panel records.
        """

        await get_character_for_user(self.repository, character_id, current_user)

        grants = await self.feature_grant_repository.get_character_features(character_id)
        return [CharacterFeatureResponse.model_validate(grant) for grant in grants]

    @use_cache(
        key_builder=lambda self, character_id, **_: (f"{cache_prefix()}:{CHARACTER_CACHE_NAMESPACE}:{character_id}"),
    )
    async def _get_character_response(self, character_id: int) -> CharacterResponse:
        """Cached response assembly for a single character (access check is NOT cached)."""

        character = await get_character_or_404(self.repository, character_id)
        return await self._to_response(character, refresh=False)

    async def create_character(self, character_data: CharacterCreate, current_user: UserResponse) -> CharacterResponse:
        """
        One-shot creation of a level-1 character owned by the caller.

        Validates that ``class_id`` (required) and, if provided,
        ``subclass_id`` (must belong to ``class_id``) /
        ``race_id``/``subrace_id`` (must belong to ``race_id``) /
        ``background_id`` reference existing records before writing
        anything — a bad reference is rejected with a clear 404 rather
        than surfacing as a raw FK IntegrityError.

        Creation contract (everything is derived server-side; the payload
        carries no ``level``/HP/skill rows):
          - the character always starts at ``level=1`` with
            ``temp_hp=0`` — leveling up happens only through the
            progression endpoint;
          - the character's GM-set level-up cap (``character_max_levels``)
            is seeded at its starting level, so it cannot level up until
            a GM raises its maximum via the GM panel;
          - skill proficiencies come from ``skill_ids`` (validated against
            the class's ``available_skills`` and ``skill_choice_count``)
            plus the background's and the race's granted skills,
            deduplicated;
          - saving throws are not written at all — they are read from the
            class on every response;
          - HP: the level-1 maximum is fixed server-side as the class's
            hit die faces + effective CON modifier; ``current_hp`` starts
            equal to it.

        After creation, the class's spell slot progression for level 1 is
        applied immediately, and the class/subclass/race/subrace/background
        features the character is entitled to are granted, along with the
        starting equipment granted by the character's class and background
        (aggregated into one stack per item). The character row, its
        proficiency rows, initial slot rows, feature grants, and starting
        items are written in one transaction (``_atomic()`` with
        ``commit=False`` on all writes): either all persist or none do.
        """

        await self._validate_references(
            class_id=character_data.class_id,
            subclass_id=character_data.subclass_id,
            race_id=character_data.race_id,
            subrace_id=character_data.subrace_id,
            background_id=character_data.background_id,
        )

        # Fetched once here so the whole flow can rely on the eager-loaded
        # available_skills / saving_throws / hit dice without refetching.
        character_class = await self.class_repository.get_by_id(character_data.class_id)
        if character_class is None:
            raise ClassNotFoundException(class_id=character_data.class_id)

        chosen_skill_ids = self._validate_chosen_skills(character_data.skill_ids, character_class)

        background_skill_ids: list[int] = []
        if character_data.background_id is not None:
            background = await self.background_repository.get_by_id(character_data.background_id)
            if background is not None:
                background_skill_ids = [skill.id for skill in background.granted_skills]

        # Same pattern as the background: get_by_id eager-loads granted_skills,
        # so no extra query is needed to collect them.
        race_skill_ids: list[int] = []
        if character_data.race_id is not None:
            race = await self.race_repository.get_by_id(character_data.race_id)
            if race is not None:
                race_skill_ids = [skill.id for skill in race.granted_skills]

        payload = character_data.model_dump(exclude={"skill_ids"})
        payload["owner_id"] = current_user.id
        payload["level"] = 1
        payload["temp_hp"] = 0

        async with self._atomic():
            character = await self.repository.create(payload, commit=False)

            # The GM-set level-up cap starts at the character's starting
            # level: it cannot level up until a GM raises its maximum.
            await self.max_level_repository.create_for_character(character.id, character.level, commit=False)

            max_hp = await self._compute_starting_max_hp(character, character_class)
            character.max_hp = max_hp
            character.current_hp = max_hp
            await self.repository.db.flush()

            await self._apply_skill_proficiencies(
                character, chosen_skill_ids, background_skill_ids, race_skill_ids, commit=False
            )
            await self._apply_spell_slot_progression(character, commit=False)

            await sync_progression_features(self.repository.db, character)

            await self._apply_starting_equipment(character, commit=False)

        character = await get_character_for_user(self.repository, character.id, current_user)
        await invalidate_character_cache(character.id)

        return await self._to_response(character, refresh=True)

    @staticmethod
    def _validate_chosen_skills(skill_ids: list[int], character_class: Class) -> list[int]:
        """
        Validate the player's class skill choices against the class rules:
        every id must be one of the class's ``available_skills`` and the
        total must not exceed ``skill_choice_count``. A non-existent skill
        id can never be in ``available_skills``, so existence needs no
        separate lookup.
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

    async def _compute_starting_max_hp(self, character: Character, character_class: Class) -> int:
        """
        Starting max HP for a level-1 character: the full hit die + CON
        modifier. There is nothing to validate — the value is always
        derived, never client-supplied.

        CON modifier comes from the *effective* CON total (base + race +
        feats), matching the level-up math in the progression service. A
        pathological ceiling below 1 (tiny die + heavily negative CON) is
        clamped to 1 so the row always satisfies the DB check constraint.
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
        Write the character's starting skill proficiencies: the validated
        class choices plus the background's and the race's granted skills,
        deduplicated across all three sources (a granted skill already
        chosen counts as one row), all with ``is_expertise=False`` —
        expertise is toggled afterwards via
        ``PATCH /{id}/gm-panel/skills/{skill_id}``.

        ``commit=False`` defers the commit so the caller can wrap this in
        a transaction with other writes — see :meth:`create_character`.
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
        Partially update a character, enforcing GM/owner access.

        Only fields present in ``CharacterUpdate`` are changeable —
        ``class_id``, ``race_id``, and ``background_id`` are set at
        creation and cannot be changed here (they aren't even fields of
        the schema, so no reference re-validation is needed on PATCH),
        and neither are ``level`` or the base ability scores (both only
        change through the progression service).
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

        Deltas follow the 5e damage/healing rules: a negative delta
        (damage) is absorbed by ``temp_hp`` first, with any overflow
        applied to ``current_hp``; a positive delta (healing) restores
        ``current_hp`` only — temp HP can't be healed. An absolute
        ``temp_hp`` is a temp-HP *gain*: it applies only when it's higher
        than the current pool (temp HP never stacks). To force-set or
        lower temp HP, PATCH the character directly (``temp_hp`` on
        ``CharacterUpdate``).

        current_hp is clamped to [0, max_hp]; temp_hp to >= 0. Providing
        both `delta` and absolute values is rejected.
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
        Resolve a healing/damage delta per 5e rules.

        Healing (``delta >= 0``) adds to ``current_hp`` only. Damage
        (``delta < 0``) drains ``temp_hp`` first — every point absorbed
        there spares ``current_hp`` — and the remainder hits ``current_hp``.
        Returns ``(new_current_hp, new_temp_hp)`` unclamped; the caller
        bounds them.
        """

        if delta >= 0:
            return current_hp + delta, temp_hp

        damage = -delta
        absorbed = min(temp_hp, damage)
        return current_hp - (damage - absorbed), temp_hp - absorbed

    async def rest(self, character_id: int, data: RestRequest, current_user: UserResponse) -> CharacterResponse:
        """
        Apply a short or long rest.

        Long rest: restore current_hp to max_hp and clear temp_hp. Known
        spells and slot totals are unchanged (the legacy ``used`` column
        is zeroed for DB-constraint hygiene, but nothing spends slots
        anymore). Short rest: accepted as a no-op placeholder until hit
        dice tracking is added.
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
        exist. Called from :meth:`create_character` only — the old
        ``"unset"`` sentinel for PATCH validation is gone, since
        ``class_id``/``subclass_id``/``race_id``/``subrace_id``/
        ``background_id`` are not fields of ``CharacterUpdate`` and
        therefore can never appear in an update (the subclass/subrace are
        changed through the progression endpoints, which re-validate
        them).
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
        Look up ``character``'s class's spell slot progression for its
        current ``level`` and sync ``CharacterSpellSlot`` totals to match.

        A class with no progression row for this level (or no ``class_id``
        at all) resolves to an empty mapping, which zeroes out any
        previously-held slots.

        ``commit=False`` defers the commit so the caller can wrap this in
        a transaction with other writes — see :meth:`create_character`.
        """

        slots_by_level = (
            await self.class_repository.get_spell_slot_progression(character.class_id, character.level)
            if character.class_id is not None
            else {}
        )
        await self.character_spell_slot_repository.apply_spell_slot_progression(
            character.id, slots_by_level, commit=commit
        )

    async def _apply_starting_equipment(self, character: Character, *, commit: bool = True) -> None:
        """
        Grant the character the starting equipment of its class and
        background.

        All ``source_items`` rows owned by the character's sources are
        collected in one query, then aggregated into one ``CharacterItem``
        stack per item (quantities summed across sources — e.g. a class
        and a background both granting a dagger produce a single stack of
        two daggers, matching D&D's combined starting-equipment feel).

        ``commit=False`` defers the commit so the caller can wrap this in
        a transaction with other writes — see :meth:`create_character`.
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

        for item_id, quantity in quantities.items():
            self.repository.db.add(CharacterItem(character_id=character.id, item_id=item_id, quantity=quantity))

        if commit:
            await self.repository.db.commit()
        else:
            await self.repository.db.flush()

    async def reapply_spell_slot_progression(self, character: Character, *, commit: bool = True) -> None:
        """
        Public wrapper around :meth:`_apply_spell_slot_progression` for
        the progression service (level-up), which owns the character's
        level writes.

        ``commit=False`` defers the commit so the caller can wrap the
        re-application in a transaction with the rest of the change.
        """

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
        Serialize a character to ``CharacterResponse``, attaching
        ``ability_scores`` from a cache row, the derived combat stats, and
        the class-derived saving throw proficiencies (there is no
        per-character saving throw storage — the class owns them).

        When ``cache_row`` is given it's used as-is (the batch listing
        path — ``get_characters`` loads all rows in one query). Otherwise
        ``CharacterStatsService.for_response`` decides: freshly
        recalculated+persisted when ``refresh`` is ``True``, else the
        existing row as-is (or ``None`` if never computed).

        ``derived`` is the precomputed hit dice / speed pair
        (``get_characters`` batch-computes it to avoid N queries per
        page); when absent it is computed here. ``armor_class`` and
        ``shield`` need no derivation — they are plain editable columns
        serialized straight off the row.

        The character's class must be eager-loaded with its
        ``saving_throws`` (see ``CharacterRepository.default_load_options``).
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
