from sqlalchemy.orm import Session

from app.features.characters.access import get_character_for_user
from app.features.characters.attacks.exceptions import AttackNotFoundException
from app.features.characters.repositories.attack_repository import AttackRepository
from app.features.characters.repositories.character_repository import CharacterRepository
from app.features.characters.rolls.dice_utils import ability_modifier, proficiency_bonus, roll_d20, roll_dice
from app.features.characters.rolls.exceptions import InvalidRollRequestException
from app.features.characters.rolls.schemas import (
    RollAttackRequest,
    RollAttackResponse,
    RollCheckRequest,
    RollCheckResponse,
)
from app.features.skills.exceptions import SkillNotFoundException
from app.features.skills.repository import SkillRepository
from app.features.users.schemas import UserResponse
from app.models.attack_model import Attack

ABILITY_FIELD_MAP = {
    "STR": "strength",
    "DEX": "dexterity",
    "CON": "constitution",
    "INT": "intelligence",
    "WIS": "wisdom",
    "CHA": "charisma",
}


class CharacterRollService:
    """
    Dice rolling: skill/ability checks, saving throws, and attack rolls.

    Pure computation on top of the character, skill, and attack repositories
    — no rolled state is persisted, the response carries the full breakdown
    (die, modifiers, total) for the caller to display.
    """

    def __init__(self, db: Session):
        self.repository = CharacterRepository(db)
        self.skill_repository = SkillRepository(db)
        self.attack_repository = AttackRepository(db)

    def roll_check(self, character_id: int, data: RollCheckRequest, current_user: UserResponse) -> RollCheckResponse:
        """
        Roll a skill check or a raw ability check/saving throw.

        Provide exactly one of `skill_id` or `ability`. `check_type` selects
        whether proficiency is looked up from skill/saving-throw
        proficiencies ("check"/"save"); for a raw ability check with no
        skill_id, proficiency is never applied.
        """

        character = get_character_for_user(self.repository, character_id, current_user)

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
        """
        Roll an attack: attack roll (d20 + ability mod + proficiency + attack
        bonus) and, on a hit, the corresponding damage roll (doubling dice on
        a natural 20).
        """

        character = get_character_for_user(self.repository, character_id, current_user)

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

    def _get_attack_or_404(self, character_id: int, attack_id: int) -> Attack:
        """Fetch an attack scoped to the character, or raise ``AttackNotFoundException``."""

        attack = self.attack_repository.get_by_id_and_character(attack_id, character_id)
        if not attack:
            raise AttackNotFoundException(character_id=character_id, attack_id=attack_id)

        return attack
