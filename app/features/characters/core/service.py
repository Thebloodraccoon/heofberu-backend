from sqlalchemy.orm import Session

from app.features.characters.access import get_character_for_user, get_character_or_404
from app.features.characters.core.exceptions import InvalidHpUpdateException, InvalidRestTypeException
from app.features.characters.core.schemas import HpUpdate, RestRequest
from app.features.characters.repositories.character_repository import CharacterRepository
from app.features.characters.schemas import CharacterCreate, CharacterResponse, CharacterUpdate
from app.features.users.schemas import UserResponse


class CharacterService:
    """
    Core character CRUD, HP management, and resting.

    Handles the character record itself. Proficiencies, spell slots, known
    spells, attacks, and dice rolling each live in their own sub-domain
    package (``proficiencies``, ``spells``, ``attacks``, ``rolls``) since
    they're independent sub-domains with their own schemas/services.
    """

    def __init__(self, db: Session):
        self.repository = CharacterRepository(db)

    def get_characters(self, current_user: UserResponse) -> list[CharacterResponse]:
        """Return every character for a GM, or only the caller's own for a player."""

        if current_user.role == "gm":
            characters = self.repository.get_all()
        else:
            characters = self.repository.get_all_by_owner(current_user.id)

        return [CharacterResponse.model_validate(character) for character in characters]

    def get_character(self, character_id: int, current_user: UserResponse) -> CharacterResponse:
        """Return a single character, enforcing GM/owner access."""

        character = get_character_for_user(self.repository, character_id, current_user)
        return CharacterResponse.model_validate(character)

    def create_character(self, character_data: CharacterCreate, current_user: UserResponse) -> CharacterResponse:
        """Create a character owned by the caller (GM or player)."""

        character = self.repository.create(character_data.model_dump(), owner_id=current_user.id)
        return CharacterResponse.model_validate(character)

    def update_character(
        self, character_id: int, update_data: CharacterUpdate, current_user: UserResponse
    ) -> CharacterResponse:
        """Partially update a character, enforcing GM/owner access."""

        character = get_character_for_user(self.repository, character_id, current_user)

        fields = update_data.model_dump(exclude_unset=True)
        updated_character = self.repository.update(character, fields)
        return CharacterResponse.model_validate(updated_character)

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
        return CharacterResponse.model_validate(updated_character)

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
            character = self.repository.update_hp(character, character.max_hp, 0)
            self.repository.reset_all_spell_slots(character_id)
            character = get_character_or_404(self.repository, character_id)

        return CharacterResponse.model_validate(character)
