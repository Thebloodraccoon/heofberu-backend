"""Character core service: CRUD, HP management, and resting."""

from typing import Any

from sqlalchemy.orm import Session

from app.constants import UserRole
from app.core.base_service import BaseService, Page, paginate
from app.features.backgrounds.exceptions import BackgroundNotFoundException
from app.features.backgrounds.repository import BackgroundRepository
from app.features.characters.ability_score.calculator import DerivedStats
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.access import get_character_for_user, get_character_or_404
from app.features.characters.core.exceptions import InvalidHpUpdateException
from app.features.characters.core.repository import CharacterRepository
from app.features.characters.core.schemas import HpUpdate, RestRequest
from app.features.characters.schemas import (
    AbilityScoresResponse,
    CharacterCreate,
    CharacterResponse,
    CharacterUpdate,
)
from app.features.characters.spells.repository import CharacterSpellSlotRepository
from app.features.classes.exceptions import ClassNotFoundException
from app.features.classes.repository import ClassRepository
from app.features.races.exceptions import RaceNotFoundException
from app.features.races.repository import RaceRepository
from app.features.users.schemas import UserResponse
from app.models import CharacterAbilityScore
from app.models.character_model import Character

# Spell slot progression policy is documented on ``CharacterService``;
# there is no ``_SPELL_SLOT_AFFECTING_FIELDS`` set anymore because
# ``CharacterUpdate`` no longer contains ``level`` — a plain PATCH can
# never invalidate spell slot totals.


class CharacterService(BaseService[Character, CharacterCreate, CharacterUpdate, CharacterResponse]):
    """
    Core character CRUD, HP management, and resting.

    Built on :class:`BaseService`, mirroring ``RaceService`` /
    ``ClassService`` / ``BackgroundService`` / ``SpellService``:
    ``CharacterRepository`` provides the full generic CRUD (no signature
    overrides), ``owner_id`` is injected into the create payload the same
    way ``created_by_id`` is for the reference features, and
    ``_get_or_404`` / ``_atomic`` / ``resolve_ids`` come from the base.

    Proficiencies, spell slots, known spells, attacks, and feats each live
    in their own subdomain package; this service owns the character record
    itself plus validating its FK references (class/race/background).
    Character progression (race change, class change, leveling up) lives
    in ``characters.progression`` and reuses this service for
    serialization and spell-slot re-application.

    Ability score cache policy is decided by
    ``CharacterStatsService`` — this service only tells it *when* a
    write might have touched ability scores:
      - ``get_character`` always refreshes before returning (fresh, cheap).
      - ``get_characters`` (listing) does NOT refresh — it returns the
        cache as-is to avoid N recalculations per page.
      - ``create_character`` always refreshes; ``update_character`` never
        refreshes, because ``CharacterUpdate`` holds no ability-affecting
        fields anymore (base scores only change via the level-up ASI, and
        race_id/class_id are not editable here).

    Derived combat stats (hit dice, speed, armor class) are computed by
    ``CharacterStatsService`` on every read, for both the detail
    and the listing path. They depend on the class, race, and equipped
    armor, so no write path here keeps them in sync — a GM editing a
    reference table is reflected on the next fetch.

    Spell slot progression policy: applied on create for the starting
    level, and re-applied by the progression service (via
    :meth:`reapply_spell_slot_progression`) whenever a character levels
    up or changes class — a plain PATCH can never touch spell slots.
    """

    repository: CharacterRepository

    def __init__(self, db: Session):
        super().__init__(
            repository=CharacterRepository(db),
            response_schema=CharacterResponse,
        )
        self.character_spell_slot_repository = CharacterSpellSlotRepository(db)
        self.class_repository = ClassRepository(db)
        self.race_repository = RaceRepository(db)
        self.background_repository = BackgroundRepository(db)
        self.stats_service = CharacterStatsService(db)

    def get_characters(
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
        characters = self.repository.get_all(
            filters=filters,
            search=search,
            order_by=Character.name,
            skip=skip,
            limit=limit,
        )
        total = self.repository.count(filters=filters, search=search)

        cache_by_id = self.stats_service.get_many_or_stale([character.id for character in characters])
        dex_totals_by_id = {
            character.id: cache_by_id[character.id].dexterity_total if character.id in cache_by_id else None
            for character in characters
        }
        derived_by_id = self.stats_service.get_many_derived(characters, dex_totals_by_id)
        return Page(
            items=[
                self._to_response(
                    character, cache_row=cache_by_id.get(character.id), derived=derived_by_id.get(character.id)
                )
                for character in characters
            ],
            total=total,
            page=page,
            size=size,
        )

    def get_character(self, character_id: int, current_user: UserResponse) -> CharacterResponse:
        """Return a single character, enforcing GM/owner access, with freshly recalculated ability scores."""

        character = get_character_for_user(self.repository, character_id, current_user)
        return self._to_response(character, refresh=True)

    def create_character(self, character_data: CharacterCreate, current_user: UserResponse) -> CharacterResponse:
        """
        Create a character owned by the caller (GM or player).

        Validates that ``class_id`` (required) and, if provided,
        ``race_id``/``background_id`` reference existing records before
        writing anything — a bad reference is rejected with a clear 404
        rather than surfacing as a raw FK IntegrityError.

        After creation, the class's spell slot progression for the
        character's starting level is applied immediately — see class
        docstring. The character row and its initial slot rows are
        written in one transaction (``_atomic()`` with ``commit=False``
        on both writes): either both persist or neither does.
        """

        self._validate_references(
            class_id=character_data.class_id,
            race_id=character_data.race_id,
            background_id=character_data.background_id,
        )

        payload = character_data.model_dump()
        payload["owner_id"] = current_user.id

        with self._atomic():
            character = self.repository.create(payload, commit=False)
            self._apply_spell_slot_progression(character, commit=False)

        return self._to_response(character, refresh=True)

    def update_character(
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

        character = get_character_for_user(self.repository, character_id, current_user)

        fields = update_data.model_dump(exclude_unset=True)
        updated_character = self.repository.update(character, fields)

        return self._to_response(updated_character, refresh=False)

    def delete_character(self, character_id: int, current_user: UserResponse) -> bool:
        """Delete a character, enforcing GM/owner access."""

        character = get_character_for_user(self.repository, character_id, current_user)
        return self.repository.delete(character)

    def update_hp(self, character_id: int, data: HpUpdate, current_user: UserResponse) -> CharacterResponse:
        """
        Update HP either via a relative delta, or by setting absolute values.

        current_hp is clamped to [0, max_hp]. temp_hp is clamped to >= 0.
        Providing both `delta` and absolute values is rejected.
        """

        character = get_character_for_user(self.repository, character_id, current_user)

        has_delta = data.delta is not None
        has_absolute = data.current_hp is not None or data.temp_hp is not None
        if has_delta and has_absolute:
            raise InvalidHpUpdateException()
        if not has_delta and not has_absolute:
            raise InvalidHpUpdateException("Provide either 'delta' or an absolute HP value.")

        if has_delta:
            new_current_hp = character.current_hp + data.delta
            new_temp_hp = character.temp_hp
        else:
            new_current_hp = data.current_hp if data.current_hp is not None else character.current_hp
            new_temp_hp = data.temp_hp if data.temp_hp is not None else character.temp_hp

        new_current_hp = max(0, min(new_current_hp, character.max_hp))
        new_temp_hp = max(0, new_temp_hp)

        updated_character = self.repository.update_hp(character, new_current_hp, new_temp_hp)
        return self._to_response(updated_character, refresh=False)

    def rest(self, character_id: int, data: RestRequest, current_user: UserResponse) -> CharacterResponse:
        """
        Apply a short or long rest.

        Long rest: restore current_hp to max_hp, clear temp_hp, and reset
        all spell slots (used -> 0). Short rest: accepted as a no-op
        placeholder until hit dice tracking is added.
        """

        character = get_character_for_user(self.repository, character_id, current_user)

        if data.type == "long":
            self.repository.update_hp(character, character.max_hp, 0)
            self.character_spell_slot_repository.reset_all_spell_slots(character_id)
            character = get_character_or_404(self.repository, character_id)

        return self._to_response(character, refresh=False)

    def _validate_references(
        self,
        *,
        class_id: int,
        race_id: int | None,
        background_id: int | None,
    ) -> None:
        """
        Raise the matching not-found exception if any given ID doesn't
        exist. Called from :meth:`create_character` only — the old
        ``"unset"`` sentinel for PATCH validation is gone, since
        ``class_id``/``race_id``/``background_id`` are not fields of
        ``CharacterUpdate`` and therefore can never appear in an update.
        """

        if not self.class_repository.exists_by_id(class_id):
            raise ClassNotFoundException(class_id=class_id)

        if race_id is not None and not self.race_repository.exists_by_id(race_id):
            raise RaceNotFoundException(race_id=race_id)

        if background_id is not None and not self.background_repository.exists_by_id(background_id):
            raise BackgroundNotFoundException(background_id=background_id)

    def _apply_spell_slot_progression(self, character: Character, *, commit: bool = True) -> None:
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
            self.class_repository.get_spell_slot_progression(character.class_id, character.level)
            if character.class_id is not None
            else {}
        )
        self.character_spell_slot_repository.apply_spell_slot_progression(character.id, slots_by_level, commit=commit)

    def reapply_spell_slot_progression(self, character: Character, *, commit: bool = True) -> None:
        """
        Public wrapper around :meth:`_apply_spell_slot_progression` for
        the progression service (class change / level-up), which owns the
        character's class/level writes.

        ``commit=False`` defers the commit so the caller can wrap the
        re-application in a transaction with the rest of the change.
        """

        self._apply_spell_slot_progression(character, commit=commit)

    def _to_response(
        self,
        character: Character,
        *,
        refresh: bool = False,
        cache_row: CharacterAbilityScore | None = None,
        derived: DerivedStats | None = None,
    ) -> CharacterResponse:
        """
        Serialize a character to ``CharacterResponse``, attaching
        ``ability_scores`` from a cache row and the derived combat stats.

        When ``cache_row`` is given it's used as-is (the batch listing
        path — ``get_characters`` loads all rows in one query). Otherwise
        ``CharacterStatsService.for_response`` decides: freshly
        recalculated+persisted when ``refresh`` is ``True``, else the
        existing row as-is (or ``None`` if never computed).

        ``derived`` is the precomputed hit dice / speed / armor class
        (``get_characters`` batch-computes it to avoid N queries per
        page); when absent it is computed here from the character's
        effective Dexterity total.
        """

        if cache_row is None:
            cache_row = self.stats_service.for_response(character, refresh=refresh)

        if derived is None:
            dex_total = cache_row.dexterity_total if cache_row is not None else None
            derived = self.stats_service.compute_derived(character, dex_total)

        response = CharacterResponse.model_validate(character)
        response.ability_scores = AbilityScoresResponse.model_validate(cache_row) if cache_row is not None else None
        response.hit_dice = derived.hit_dice
        response.speed = derived.speed
        response.armor_class = derived.armor_class
        return response
