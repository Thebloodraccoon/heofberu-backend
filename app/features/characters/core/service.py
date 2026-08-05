"""Character core service: CRUD, HP management, and resting."""

from sqlalchemy.orm import Session

from app.features.backgrounds.exceptions import BackgroundNotFoundException
from app.features.backgrounds.repository import BackgroundRepository
from app.features.characters.ability_score.service import CharacterAbilityCacheService
from app.features.characters.access import get_character_for_user, get_character_or_404
from app.features.characters.core.exceptions import InvalidHpUpdateException, InvalidRestTypeException
from app.features.characters.core.repository import CharacterRepository
from app.features.characters.core.schemas import HpUpdate, RestRequest
from app.features.characters.schemas import (
    AbilityScoresResponse,
    CharacterCreate,
    CharacterResponse,
    CharacterUpdate,
)
from app.features.characters.spells.repository import CharacterSpellRepository
from app.features.classes.exceptions import ClassNotFoundException
from app.features.classes.repository import ClassRepository
from app.features.races.exceptions import RaceNotFoundException
from app.features.races.repository import RaceRepository
from app.features.users.schemas import UserResponse
from app.models.character_model import Character

# Fields on CharacterUpdate that, if changed, invalidate the character's
# actual spell slot totals (CharacterSpellSlot) and require re-applying
# the class's spell slot progression — either because the class itself
# changed (different/no progression table) or the level did (different
# row within the same table).
_SPELL_SLOT_AFFECTING_FIELDS = {"class_id", "level"}


class CharacterService:
    """
    Core character CRUD, HP management, and resting.

    Handles the character record itself, plus validating its foreign
    keys (class/race/background). Proficiencies, spell slots, known
    spells, attacks, and feats each live in their own subdomain package
    since they're independent subdomains with their own
    schemas/services.

    Ability score cache policy is decided by ``CharacterAbilityCacheService``
    (see that class), not here — this service only tells it *when* a
    write might have touched ability scores, via
    ``CharacterAbilityCacheService.fields_affect_ability_scores`` (the
    ``ABILITY_AFFECTING_FIELDS`` set):
      - ``get_character`` (single record, by ID) always calls
        ``refresh`` before returning — this is the one read path
        guaranteed to be fresh, and it's cheap since it's scoped to one
        character.
      - ``get_characters`` (listing) intentionally does NOT refresh —
        it returns whatever ``get_or_stale`` finds, to avoid N
        recalculations per page. A character that's never been fetched
        individually (and therefore has no cache row yet) shows
        ``ability_scores`` as ``None``.
      - ``create_character`` always refreshes after writing.
        ``update_character`` refreshes only when the PATCHed fields
        intersect ``ABILITY_AFFECTING_FIELDS``; otherwise the existing
        cache row is read as-is.

    Spell slot progression policy (see
    ``ClassRepository.get_spell_slot_progression`` /
    ``CharacterSpellRepository.apply_spell_slot_progression``):
      - ``create_character`` always applies the new character's class's
        progression for its starting ``level``, so a level-1 caster
        already has ``CharacterSpellSlot`` rows on creation instead of
        needing a manual PATCH to ``/spell-slots`` first.
      - ``update_character`` re-applies the progression whenever
        ``level`` is part of the PATCH — a level-up grants/adjusts slot
        totals automatically. (``class_id`` is not editable via the
        update schema; a class change requires recreating the character.)
        Any ``used`` already recorded on a level is preserved unless it
        would now exceed the new ``total``, in which case it's clamped
        down — see ``apply_spell_slot_progression`` for the exact
        semantics.
      - A class/level pair with no progression rows simply applies an
        empty mapping, which zeroes out any slots the character
        previously had — appropriate for e.g. multiclassing away from a
        caster.
    """

    def __init__(self, db: Session):
        self.db = db
        self.repository = CharacterRepository(db)
        self.character_spell_repository = CharacterSpellRepository(db)
        self.class_repository = ClassRepository(db)
        self.race_repository = RaceRepository(db)
        self.background_repository = BackgroundRepository(db)
        self.ability_cache_service = CharacterAbilityCacheService(db)

    def get_characters(self, current_user: UserResponse) -> list[CharacterResponse]:
        """
        Return every character for a GM, or only the caller's own for a
        player. Ability scores reflect the last-computed cache, not a
        fresh recalculation — see class docstring.
        """

        if current_user.role == "gm":
            characters = self.repository.get_all()
        else:
            characters = self.repository.get_all_by_owner(current_user.id)

        return [self._to_response(character, refresh=False) for character in characters]

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
        docstring.
        """

        self._validate_references(
            class_id=character_data.class_id,
            race_id=character_data.race_id,
            background_id=character_data.background_id,
        )

        character = self.repository.create(character_data.model_dump(), owner_id=current_user.id)

        self._apply_spell_slot_progression(character)

        return self._to_response(character, refresh=True)

    def update_character(
        self, character_id: int, update_data: CharacterUpdate, current_user: UserResponse
    ) -> CharacterResponse:
        """
        Partially update a character, enforcing GM/owner access.

        Only fields present in ``CharacterUpdate`` are changeable —
        ``class_id``, ``race_id``, and ``background_id`` are set at
        creation and cannot be changed here. If ``level`` is part of the
        update, the character's spell slot totals are re-synced to the
        new level's progression — see class docstring.
        """

        character = get_character_for_user(self.repository, character_id, current_user)

        fields = update_data.model_dump(exclude_unset=True)

        self._validate_references(
            class_id=fields.get("class_id") if "class_id" in fields else "unset",
            race_id=fields.get("race_id") if "race_id" in fields else "unset",
            background_id=fields.get("background_id") if "background_id" in fields else "unset",
        )

        updated_character = self.repository.update(character, fields)

        if _SPELL_SLOT_AFFECTING_FIELDS & fields.keys():
            self._apply_spell_slot_progression(updated_character)

        refresh = self.ability_cache_service.fields_affect_ability_scores(fields.keys())
        return self._to_response(updated_character, refresh=refresh)

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

        Long rest: restore current_hp to max_hp, clear temp_hp, and reset all
        spell slots (used -> 0).
        Short rest: no automatic HP or spell slot recovery is applied here —
        5e short rests recover HP via spent hit dice, which isn't modeled yet,
        and only certain caster subclasses recover slots on a short rest. The
        endpoint accepts "short" as a no-op placeholder so the rest-type
        contract is already in place for when hit dice tracking is added.
        """

        character = get_character_for_user(self.repository, character_id, current_user)

        if data.type not in ("short", "long"):
            raise InvalidRestTypeException(data.type)

        if data.type == "long":
            self.repository.update_hp(character, character.max_hp, 0)
            self.character_spell_repository.reset_all_spell_slots(character_id)
            character = get_character_or_404(self.repository, character_id)

        return self._to_response(character, refresh=False)

    def _validate_references(
        self,
        *,
        class_id: int | str,
        race_id: int | None | str,
        background_id: int | None | str,
    ) -> None:
        """
        Raise the matching not-found exception if any given ID doesn't
        exist. All three accept the sentinel string ``"unset"`` to mean
        "not included in this PATCH" (skip validation).

        ``race_id``/``background_id`` additionally accept ``None`` to mean
        "explicitly clearing the field" (also skip validation — there's
        nothing to check, since those columns are nullable). ``class_id``
        never receives ``None``: it is required on create and is not a
        field of ``CharacterUpdate``, so it is either ``"unset"`` or a
        concrete id to check.
        """

        if class_id != "unset" and not self.class_repository.exists_by_id(class_id):
            raise ClassNotFoundException(class_id=class_id)

        if race_id not in (None, "unset") and not self.race_repository.exists_by_id(race_id):
            raise RaceNotFoundException(race_id=race_id)

        if background_id not in (None, "unset") and not self.background_repository.exists_by_id(background_id):
            raise BackgroundNotFoundException(background_id=background_id)

    def _apply_spell_slot_progression(self, character: Character) -> None:
        """
        Look up ``character``'s class's spell slot progression for its
        current ``level`` and sync ``CharacterSpellSlot`` totals to match.

        A class with no progression row for this level (or no
        ``class_id`` at all, which shouldn't happen since it's required,
        but guarded anyway) resolves to an empty mapping, which zeroes
        out any previously-held slots — see class docstring.
        """

        slots_by_level = (
            self.class_repository.get_spell_slot_progression(character.class_id, character.level)
            if character.class_id is not None
            else {}
        )
        self.character_spell_repository.apply_spell_slot_progression(character.id, slots_by_level)

    def _to_response(self, character: Character, *, refresh: bool) -> CharacterResponse:
        """
        Serialize a character to ``CharacterResponse``, attaching
        ``ability_scores`` either freshly recalculated (and persisted to
        the cache, via ``CharacterAbilityCacheService.refresh``) or read
        as-is from the existing cache row (via ``get_or_stale``).
        """

        if refresh:
            cache_row = self.ability_cache_service.refresh(character)
        else:
            cache_row = self.ability_cache_service.get_or_stale(character.id)

        response = CharacterResponse.model_validate(character)
        response.ability_scores = AbilityScoresResponse.model_validate(cache_row) if cache_row is not None else None
        return response
