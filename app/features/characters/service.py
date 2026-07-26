from sqlalchemy.orm import Session

from app.exceptions.character_exceptions import (
    AttackNotFoundException,
    CharacterAccessDeniedException,
    CharacterNotFoundException,
    CharacterSpellAlreadyKnownException,
    CharacterSpellNotFoundException,
    InvalidHpUpdateException,
    InvalidRestTypeException,
    InvalidRollRequestException,
    InvalidSkillIdsException,
    InvalidSpellSlotUsageException,
)
from app.exceptions.skill_exceptions import SkillNotFoundException
from app.exceptions.spell_exceptions import SpellNotFoundException
from app.features.characters.attack_repository import AttackRepository
from app.features.characters.dice_utils import (
    ability_modifier,
    proficiency_bonus,
    roll_d20,
    roll_dice,
)
from app.features.characters.repository import CharacterRepository
from app.features.characters.schemas import (
    AttackCreate,
    AttackResponse,
    AttackUpdate,
    CharacterCreate,
    CharacterResponse,
    CharacterSpellAdd,
    CharacterSpellPrepareUpdate,
    CharacterSpellResponse,
    CharacterUpdate,
    HpUpdate,
    RestRequest,
    RollAttackRequest,
    RollAttackResponse,
    RollCheckRequest,
    RollCheckResponse,
    SavingThrowProficienciesUpdate,
    SkillProficienciesUpdate,
    SpellSlotResponse,
    SpellSlotUpdate,
)
from app.features.skills.repository import SkillRepository
from app.features.spells.repository import SpellRepository
from app.features.users.schemas import UserResponse

ABILITY_FIELD_MAP = {
    "STR": "strength",
    "DEX": "dexterity",
    "CON": "constitution",
    "INT": "intelligence",
    "WIS": "wisdom",
    "CHA": "charisma",
}


class CharacterService:
    def __init__(self, db: Session):
        self.repository = CharacterRepository(db)
        self.skill_repository = SkillRepository(db)
        self.spell_repository = SpellRepository(db)
        self.attack_repository = AttackRepository(db)

    def get_characters(self, current_user: UserResponse) -> list[CharacterResponse]:
        """GM sees every character. Players see only their own."""
        if current_user.role == "gm":
            characters = self.repository.get_all()
        else:
            characters = self.repository.get_all_by_owner(current_user.id)

        return [CharacterResponse.model_validate(character) for character in characters]

    def get_character(self, character_id: int, current_user: UserResponse) -> CharacterResponse:
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)
        return CharacterResponse.model_validate(character)

    def create_character(self, character_data: CharacterCreate, current_user: UserResponse) -> CharacterResponse:
        """Both GM and players can create characters, always owned by themselves."""
        character = self.repository.create(character_data.model_dump(), owner_id=current_user.id)
        return CharacterResponse.model_validate(character)

    def update_character(
        self, character_id: int, update_data: CharacterUpdate, current_user: UserResponse
    ) -> CharacterResponse:
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)

        fields = update_data.model_dump(exclude_unset=True)
        updated_character = self.repository.update(character, fields)
        return CharacterResponse.model_validate(updated_character)

    def delete_character(self, character_id: int, current_user: UserResponse) -> bool:
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)
        return self.repository.delete(character)

    def update_hp(self, character_id: int, data: HpUpdate, current_user: UserResponse) -> CharacterResponse:
        """Update HP either via a relative delta, or by setting absolute values.

        current_hp is clamped to [0, max_hp]. temp_hp is clamped to >= 0.
        Providing both `delta` and absolute values is rejected.
        """
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)

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

    def set_skill_proficiencies(
        self, character_id: int, data: SkillProficienciesUpdate, current_user: UserResponse
    ) -> CharacterResponse:
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)

        skill_ids = [item.skill_id for item in data.skill_proficiencies]
        if skill_ids:
            found_skills = self.skill_repository.get_skills_by_ids(skill_ids)
            found_ids = {skill.id for skill in found_skills}
            missing_ids = [skill_id for skill_id in skill_ids if skill_id not in found_ids]
            if missing_ids:
                raise InvalidSkillIdsException(missing_ids)

        proficiencies = [
            {"skill_id": item.skill_id, "is_expertise": item.is_expertise} for item in data.skill_proficiencies
        ]
        updated_character = self.repository.set_skill_proficiencies(character, proficiencies)
        return CharacterResponse.model_validate(updated_character)

    def set_saving_throw_proficiencies(
        self, character_id: int, data: SavingThrowProficienciesUpdate, current_user: UserResponse
    ) -> CharacterResponse:
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)

        updated_character = self.repository.set_saving_throw_proficiencies(character, data.saving_throws)
        return CharacterResponse.model_validate(updated_character)

    def get_spell_slots(self, character_id: int, current_user: UserResponse) -> list[SpellSlotResponse]:
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)

        slots = self.repository.get_all_spell_slots(character_id)
        return [SpellSlotResponse.model_validate(slot) for slot in slots]

    def update_spell_slot(
        self, character_id: int, data: SpellSlotUpdate, current_user: UserResponse
    ) -> SpellSlotResponse:
        """Spend or restore a spell slot at a given level.

        If no entry exists yet for this level, one is created — this also
        covers initially granting a character's slots (e.g. total=4, used=0).
        """
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)

        existing = self.repository.get_spell_slot(character_id, data.level)
        current_total = existing.total if existing else 0
        current_used = existing.used if existing else 0

        new_total = data.total if data.total is not None else current_total
        new_used = data.used if data.used is not None else current_used

        if new_used < 0 or new_used > new_total:
            raise InvalidSpellSlotUsageException()

        slot = self.repository.upsert_spell_slot(character_id, data.level, new_total, new_used)
        return SpellSlotResponse.model_validate(slot)

    def rest(self, character_id: int, data: RestRequest, current_user: UserResponse) -> CharacterResponse:
        """Apply a short or long rest.

        Long rest: restore current_hp to max_hp, clear temp_hp, and reset all
        spell slots (used -> 0).
        Short rest: no automatic HP or spell slot recovery is applied here —
        5e short rests recover HP via spent hit dice, which isn't modeled yet,
        and only certain caster subclasses recover slots on a short rest. The
        endpoint accepts "short" as a no-op placeholder so the rest-type
        contract is already in place for when hit dice tracking is added.
        """
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)

        if data.type not in ("short", "long"):
            raise InvalidRestTypeException(data.type)

        if data.type == "long":
            character = self.repository.update_hp(character, character.max_hp, 0)
            self.repository.reset_all_spell_slots(character_id)
            character = self._get_character_or_404(character_id)

        return CharacterResponse.model_validate(character)

    def get_known_spells(self, character_id: int, current_user: UserResponse) -> list[CharacterSpellResponse]:
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)

        known_spells = self.repository.get_known_spells(character_id)
        return [CharacterSpellResponse.model_validate(cs) for cs in known_spells]

    def add_known_spell(
        self, character_id: int, data: CharacterSpellAdd, current_user: UserResponse
    ) -> CharacterSpellResponse:
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)

        spell = self.spell_repository.get_by_id(data.spell_id)
        if not spell:
            raise SpellNotFoundException(spell_id=data.spell_id)

        existing = self.repository.get_known_spell(character_id, data.spell_id)
        if existing:
            raise CharacterSpellAlreadyKnownException(character_id=character_id, spell_id=data.spell_id)

        character_spell = self.repository.add_known_spell(character_id, data.spell_id)
        return CharacterSpellResponse.model_validate(character_spell)

    def remove_known_spell(self, character_id: int, spell_id: int, current_user: UserResponse) -> bool:
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)

        character_spell = self._get_known_spell_or_404(character_id, spell_id)
        return self.repository.remove_known_spell(character_spell)

    def set_spell_prepared(
        self,
        character_id: int,
        spell_id: int,
        data: CharacterSpellPrepareUpdate,
        current_user: UserResponse,
    ) -> CharacterSpellResponse:
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)

        character_spell = self._get_known_spell_or_404(character_id, spell_id)
        updated = self.repository.set_spell_prepared(character_spell, data.is_prepared)
        return CharacterSpellResponse.model_validate(updated)

    def get_attacks(self, character_id: int, current_user: UserResponse) -> list[AttackResponse]:
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)

        attacks = self.attack_repository.get_all_by_character(character_id)
        return [AttackResponse.model_validate(attack) for attack in attacks]

    def create_attack(self, character_id: int, data: AttackCreate, current_user: UserResponse) -> AttackResponse:
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)

        attack = self.attack_repository.create(data.model_dump(), character_id)
        return AttackResponse.model_validate(attack)

    def update_attack(
        self, character_id: int, attack_id: int, data: AttackUpdate, current_user: UserResponse
    ) -> AttackResponse:
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)

        attack = self._get_attack_or_404(character_id, attack_id)
        fields = data.model_dump(exclude_unset=True)
        updated_attack = self.attack_repository.update(attack, fields)
        return AttackResponse.model_validate(updated_attack)

    def delete_attack(self, character_id: int, attack_id: int, current_user: UserResponse) -> bool:
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)

        attack = self._get_attack_or_404(character_id, attack_id)
        return self.attack_repository.delete(attack)

    def roll_check(self, character_id: int, data: RollCheckRequest, current_user: UserResponse) -> RollCheckResponse:
        """Roll a skill check or a raw ability check/saving throw.

        Provide exactly one of `skill_id` or `ability`. `check_type` selects
        whether proficiency is looked up from skill/saving-throw
        proficiencies ("check"/"save"); for a raw ability check with no
        skill_id, proficiency is never applied.
        """
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)

        if data.check_type not in ("check", "save"):
            raise InvalidRollRequestException(f"Invalid check_type: '{data.check_type}'. Expected 'check' or 'save'.")
        if data.skill_id is not None and data.ability is not None:
            raise InvalidRollRequestException("Provide only one of 'skill_id' or 'ability'.")
        if data.skill_id is None and data.ability is None:
            raise InvalidRollRequestException("Provide one of 'skill_id' or 'ability'.")

        if data.skill_id is not None:
            skill = self.skill_repository.get_by_id(data.skill_id)
            if not skill:
                raise SkillNotFoundException(skill_id=data.skill_id)

            ability = skill.ability
            proficiency = self.repository.get_skill_proficiency(character_id, data.skill_id)
            is_proficient = proficiency is not None
            expertise_multiplier = 2 if (proficiency and proficiency.is_expertise) else 1
        else:
            ability = data.ability
            if data.check_type == "save":
                proficiency = self.repository.get_saving_throw_proficiency(character_id, ability)
                is_proficient = proficiency is not None
            else:
                is_proficient = False
            expertise_multiplier = 1

        ability_field = ABILITY_FIELD_MAP.get(str(ability), None)
        score = getattr(character, ability_field, 10) if ability_field else 10
        mod = ability_modifier(score)
        prof_bonus = proficiency_bonus(character.level) if is_proficient else 0
        prof_bonus *= expertise_multiplier

        d20 = roll_d20()
        total = d20 + mod + prof_bonus

        return RollCheckResponse(
            d20_roll=d20,
            ability=ability,
            ability_modifier=mod,
            proficiency_bonus=prof_bonus,
            is_proficient=is_proficient,
            total=total,
            check_type=data.check_type,
            skill_id=data.skill_id,
        )

    def roll_attack(self, character_id: int, data: RollAttackRequest, current_user: UserResponse) -> RollAttackResponse:
        character = self._get_character_or_404(character_id)
        self._check_access(character, current_user)

        attack = self._get_attack_or_404(character_id, data.attack_id)

        ability_field = ABILITY_FIELD_MAP.get(str(attack.ability), None)
        score = getattr(character, ability_field, 10) if ability_field else 10
        mod = ability_modifier(score)
        prof_bonus = proficiency_bonus(character.level) if attack.is_proficient else 0

        d20 = roll_d20()
        is_critical = d20 == 20
        attack_total = d20 + mod + prof_bonus + attack.bonus_attack

        damage_roll = roll_dice(attack.damage_dice)
        if is_critical:
            damage_roll += roll_dice(attack.damage_dice)
        damage_modifier = mod + attack.bonus_damage
        damage_total = damage_roll + damage_modifier

        return RollAttackResponse(
            attack_id=attack.id,
            attack_name=attack.name,
            d20_roll=d20,
            ability_modifier=mod,
            proficiency_bonus=prof_bonus,
            is_proficient=attack.is_proficient,
            attack_total=attack_total,
            damage_dice=attack.damage_dice,
            damage_roll=damage_roll,
            damage_modifier=damage_modifier,
            damage_total=damage_total,
            is_critical=is_critical,
        )

    def _get_attack_or_404(self, character_id: int, attack_id: int):
        attack = self.attack_repository.get_by_id_and_character(attack_id, character_id)
        if not attack:
            raise AttackNotFoundException(character_id=character_id, attack_id=attack_id)
        return attack

    def _get_known_spell_or_404(self, character_id: int, spell_id: int):
        character_spell = self.repository.get_known_spell(character_id, spell_id)
        if not character_spell:
            raise CharacterSpellNotFoundException(character_id=character_id, spell_id=spell_id)
        return character_spell

    def _get_character_or_404(self, character_id: int):
        character = self.repository.get_by_id(character_id)
        if not character:
            raise CharacterNotFoundException(character_id=character_id)
        return character

    @staticmethod
    def _check_access(character, current_user: UserResponse) -> None:
        """GM can access any character. Players can only access their own."""
        if current_user.role == "gm":
            return

        if character.owner_id != current_user.id:
            raise CharacterAccessDeniedException()
