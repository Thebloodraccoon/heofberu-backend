"""Character crud service: reads, updates, HP management and resting."""

from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import use_cache
from app.core.exceptions import GmAccessException
from app.core.pagination import CursorPage, Page, cursor_page, decode_cursor, keyset_condition, paginate
from app.features.characters.ability_score.calculator import BASE_FIELD_BY_ABILITY
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.access import check_character_access, is_gm
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.cache import CHARACTER_CACHE_TTL, character_cache_key
from app.features.characters.crud.creation import CharacterCreationService
from app.features.characters.crud.repository import CharacterRepository
from app.features.characters.crud.rules import resolve_hp_update, validate_hp_update
from app.features.characters.crud.schemas import HpUpdate, RestRequest
from app.features.characters.exceptions import CharacterNotFoundException, GmOnlyFieldException
from app.features.characters.schemas import (
    AbilityScoresResponse,
    AbilityStatsView,
    CharacterCreate,
    CharacterResponse,
    CharacterStatsResponse,
    CharacterUpdate,
)
from app.features.characters.spells.repository import CharacterSpellSlotRepository
from app.features.users.schemas import UserResponse
from app.models import CharacterAbilityScore
from app.models.character.character_model import Character


class CharacterService(CharacterSubDomainService):
    """
    Core character reads, updates, HP management and resting. Creation is
    delegated to :class:`CharacterCreationService`. Owns the response cache
    (access control is never cached) and the ability-score cache write
    policy: reads never recompute.
    """

    repository: CharacterRepository
    # Reads and writes here need the row freshly re-read (``populate_existing``).
    _light_character_fetch = False

    def __init__(self, db: AsyncSession):
        """Set up the character service and its collaborators."""

        super().__init__(db)
        self.stats_service = CharacterStatsService(db)
        self.creation = CharacterCreationService(db, self.stats_service)
        self.character_spell_slot_repository = CharacterSpellSlotRepository(db)

    async def list_characters(
        self,
        current_user: UserResponse,
        *,
        scope: Literal["mine", "all"],
        search: str | None = None,
        class_id: int | None = None,
        page: int = 1,
        size: int = 10,
        cursor: str | None = None,
        use_cursor: bool = False,
    ) -> Page[CharacterResponse] | CursorPage[CharacterResponse]:
        """
        One listing for every audience, ordered by ``(name, id)``.

        ``scope="mine"`` is the caller's own characters (any role, GMs included);
        ``scope="all"`` is every user's and GM-only (403 otherwise). With
        ``use_cursor`` the result is a keyset ``CursorPage``, else an offset ``Page``.
        """

        if scope == "all":
            if not is_gm(current_user):
                raise GmAccessException()
            owner_id = None
        else:
            owner_id = current_user.id

        filters: dict[str, Any] = {}
        if owner_id is not None:
            filters["owner_id"] = owner_id
        if class_id is not None:
            filters["class_id"] = class_id
        filters = filters or None

        if use_cursor:
            conditions = []
            if cursor is not None:
                conditions.append(keyset_condition(Character.name, Character.id, decode_cursor(cursor, "name")))
            characters = await self.repository.get_all(
                filters=filters, search=search, order_by=Character.name, limit=size + 1, conditions=conditions
            )
            characters, next_cursor = cursor_page(characters, size, "name", lambda c: (c.name, c.id))
            return CursorPage(items=await self._serialize_many(characters), next_cursor=next_cursor, size=size)

        skip, limit = paginate(page, size)
        characters = await self.repository.get_all(
            filters=filters, search=search, order_by=Character.name, skip=skip, limit=limit
        )
        total = await self.repository.count(filters=filters, search=search)
        return Page(items=await self._serialize_many(characters), total=total, page=page, size=size)

    async def _serialize_many(self, characters: list[Character]) -> list[CharacterResponse]:
        """Serialize listed characters with their cached ability scores and derived hit dice."""

        cache_by_id = await self.stats_service.get_many_or_stale([character.id for character in characters])
        derived_by_id = await self.stats_service.get_many_derived(characters)
        return [
            self._serialize(character, cache_by_id.get(character.id), derived_by_id[character.id].hit_dice)
            for character in characters
        ]

    async def get_character(self, character_id: int, current_user: UserResponse) -> CharacterResponse:
        """
        Return a single character, enforcing GM/owner access. The response
        assembly is cached per character so repeated reads skip the
        ability-score and class lookups; the character row itself is read
        once for the access check and reused on a cache miss.
        """

        character = await self.get_character_for_user(character_id, current_user)
        return await self._get_character_response(character)

    async def get_stats(self, character_id: int, current_user: UserResponse) -> CharacterStatsResponse:
        """
        Each ability's ORIGINAL base value next to its COMPUTED effective
        total, with the source contributions that produced it.
        """

        character = await self.get_character_for_user(character_id, current_user)
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

    @use_cache(ttl=CHARACTER_CACHE_TTL, key_builder=lambda self, character, **_: character_cache_key(character.id))
    async def _get_character_response(self, character: Character) -> CharacterResponse:
        """Cached response assembly for an already access-checked character."""

        return await self._response_for(character)

    async def create_character(self, character_data: CharacterCreate, current_user: UserResponse) -> CharacterResponse:
        """
        One-shot creation of a level-1 character owned by the caller.

        Everything is validated first (:meth:`CharacterCreationService.prepare`),
        then the character, its proficiencies, slots, feature grants, ability
        cache row, starting HP, backstory and items are written in one
        transaction.
        """

        plan = await self.creation.prepare(character_data, current_user.id)

        async with self._atomic():
            character, ability_scores = await self.creation.persist(plan)

        return self._serialize(character, ability_scores, plan.character_class.hit_dice.value)

    async def update_character(
        self, character_id: int, update_data: CharacterUpdate, current_user: UserResponse
    ) -> CharacterResponse:
        """
        Partially update a character, enforcing GM/owner access. Only fields
        present in ``CharacterUpdate`` are changeable; ``current_hp`` is
        clamped to ``max_hp`` and ``inspiration`` can only be raised by a GM.
        """

        character = await self.get_character_for_user(character_id, current_user)

        fields = update_data.model_dump(exclude_unset=True)
        if fields.get("inspiration", 0) > character.inspiration and not is_gm(current_user):
            raise GmOnlyFieldException("inspiration")
        if "current_hp" in fields:
            fields["current_hp"] = min(fields["current_hp"], character.max_hp)

        updated_character = await self.repository.update(character, fields)
        await self._invalidate_character(character_id)
        return await self._response_for(updated_character)

    async def delete_character(self, character_id: int, current_user: UserResponse) -> bool:
        """Delete a character, enforcing GM/owner access."""

        character = await self.get_character_for_user(character_id, current_user)
        deleted = await self.repository.delete(character)
        await self._invalidate_character(character_id)
        return deleted

    async def update_hp(self, character_id: int, data: HpUpdate, current_user: UserResponse) -> CharacterResponse:
        """
        Update HP either via a relative delta, or by setting absolute values
        (see :func:`~app.features.characters.crud.rules.resolve_hp_update`;
        mixing the two is a 400). The row is locked for the read-modify-write,
        so concurrent damage/healing is applied one after the other, never lost.
        """

        async with self._atomic():
            character = await self._get_locked_for_user(character_id, current_user)
            validate_hp_update(data)

            current_hp, temp_hp = resolve_hp_update(character.current_hp, character.temp_hp, character.max_hp, data)
            await self.repository.update_hp(character, current_hp, temp_hp, commit=False)
            await self._invalidate_character(character_id)

        return await self._response_for(character)

    async def rest(self, character_id: int, data: RestRequest, current_user: UserResponse) -> CharacterResponse:
        """
        Apply a short or long rest. A long rest restores HP to max, clears
        temp HP and resets spell-slot usage in one transaction; a short rest
        is a no-op placeholder until hit dice are tracked.
        """

        if data.type != "long":
            character = await self.get_character_for_user(character_id, current_user)
            return await self._response_for(character)

        async with self._atomic():
            character = await self._get_locked_for_user(character_id, current_user)
            await self.repository.update_hp(character, character.max_hp, 0, commit=False)
            await self.character_spell_slot_repository.reset_all_spell_slots(character_id, commit=False)
            await self._invalidate_character(character_id)

        return await self._response_for(character)

    async def reapply_spell_slot_progression(self, character: Character, *, commit: bool = True) -> None:
        """Re-sync the character's spell-slot totals to its class progression (used by the progression service)."""

        await self.creation.apply_spell_slot_progression(character, commit=commit)

    async def _get_locked_for_user(self, character_id: int, current_user: UserResponse) -> Character:
        """Fetch the character row ``FOR UPDATE`` and enforce GM/owner access."""

        character = await self.repository.get_for_update(character_id)
        if character is None:
            raise CharacterNotFoundException(character_id=character_id)

        check_character_access(character, current_user)
        return character

    async def _response_for(self, character: Character) -> CharacterResponse:
        """Serialize a character with its stored ability-score row and derived hit dice."""

        cache_row = await self.stats_service.get_or_stale(character.id)
        derived = await self.stats_service.compute_derived(character)
        return self._serialize(character, cache_row, derived.hit_dice)

    @staticmethod
    def _serialize(character: Character, cache_row: CharacterAbilityScore | None, hit_dice: str) -> CharacterResponse:
        """Build ``CharacterResponse``: ability totals come from the cache row, hit dice from the class."""

        response = CharacterResponse.model_validate(character)
        response.ability_scores = AbilityScoresResponse.model_validate(cache_row) if cache_row is not None else None
        response.hit_dice = hit_dice
        return response
