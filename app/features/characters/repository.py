from sqlalchemy.orm import Session

from app.core.repository import BaseRepository
from app.models.character_association_models import (
    CharacterSavingThrowProficiency,
    CharacterSkillProficiency,
    CharacterSpellSlot,
)
from app.models.character_model import Character
from app.models.character_spell_model import CharacterSpell


class CharacterRepository(BaseRepository[Character]):
    def __init__(self, db: Session):
        super().__init__(Character, db)

    def get_all(self) -> list[Character]:
        """Get all characters, ordered by name. GM-only use case.

        Overrides base pagination-based get_all.
        """
        return self.db.query(Character).order_by(Character.name).all()

    def get_all_by_owner(self, owner_id: int) -> list[Character]:
        """Get characters owned by a specific user. Player use case."""
        return (
            self.db.query(Character)
            .filter(Character.owner_id == owner_id)
            .order_by(Character.name)
            .all()
        )

    def create(self, character_data: dict, owner_id: int) -> Character:  # type: ignore[override]
        """Create a character for a given owner (overrides base create signature)."""
        character = Character(**character_data, owner_id=owner_id)
        self.db.add(character)
        self.db.commit()
        self.db.refresh(character)
        return character

    def update_hp(self, character: Character, current_hp: int, temp_hp: int) -> Character:
        """Set current and temp HP directly. Bounds/validation happen in the service."""
        character.current_hp = current_hp
        character.temp_hp = temp_hp
        self.db.commit()
        self.db.refresh(character)
        return character

    def get_skill_proficiency(
        self, character_id: int, skill_id: int
    ) -> CharacterSkillProficiency | None:
        return (
            self.db.query(CharacterSkillProficiency)
            .filter(
                CharacterSkillProficiency.character_id == character_id,
                CharacterSkillProficiency.skill_id == skill_id,
            )
            .first()
        )

    def get_saving_throw_proficiency(
        self, character_id: int, ability: str
    ) -> CharacterSavingThrowProficiency | None:
        return (
            self.db.query(CharacterSavingThrowProficiency)
            .filter(
                CharacterSavingThrowProficiency.character_id == character_id,
                CharacterSavingThrowProficiency.ability == ability,
            )
            .first()
        )

    def set_skill_proficiencies(
        self, character: Character, proficiencies: list[dict]
    ) -> Character:
        """Replace all skill proficiencies for a character with the given list.

        Each item is expected to have 'skill_id' and 'is_expertise'.
        """
        self.db.query(CharacterSkillProficiency).filter(
            CharacterSkillProficiency.character_id == character.id
        ).delete()

        for item in proficiencies:
            self.db.add(
                CharacterSkillProficiency(
                    character_id=character.id,
                    skill_id=item["skill_id"],
                    is_expertise=item.get("is_expertise", False),
                )
            )

        self.db.commit()
        self.db.refresh(character)
        return character

    def set_saving_throw_proficiencies(
        self, character: Character, abilities: list[str]
    ) -> Character:
        """Replace all saving throw proficiencies for a character with the given list."""
        self.db.query(CharacterSavingThrowProficiency).filter(
            CharacterSavingThrowProficiency.character_id == character.id
        ).delete()

        for ability in abilities:
            self.db.add(
                CharacterSavingThrowProficiency(character_id=character.id, ability=ability)
            )

        self.db.commit()
        self.db.refresh(character)
        return character

    def get_spell_slot(self, character_id: int, level: str) -> CharacterSpellSlot | None:
        return (
            self.db.query(CharacterSpellSlot)
            .filter(
                CharacterSpellSlot.character_id == character_id,
                CharacterSpellSlot.spell_level == level,
            )
            .first()
        )

    def upsert_spell_slot(
        self, character_id: int, level: str, total: int | None, used: int | None
    ) -> CharacterSpellSlot:
        """Create or update the spell slot entry for a given level.

        If the entry doesn't exist yet, it's created with the given values
        (defaulting missing fields to 0). Validation of the used<=total
        invariant happens in the service before this is called.
        """
        slot = self.get_spell_slot(character_id, level)
        if slot is None:
            slot = CharacterSpellSlot(
                character_id=character_id,
                spell_level=level,
                total=total if total is not None else 0,
                used=used if used is not None else 0,
            )
            self.db.add(slot)
        else:
            if total is not None:
                slot.total = total
            if used is not None:
                slot.used = used

        self.db.commit()
        self.db.refresh(slot)
        return slot

    def get_all_spell_slots(self, character_id: int) -> list[CharacterSpellSlot]:
        return (
            self.db.query(CharacterSpellSlot)
            .filter(CharacterSpellSlot.character_id == character_id)
            .all()
        )

    def reset_all_spell_slots(self, character_id: int) -> None:
        """Set used=0 for every spell slot entry of the character (long rest)."""
        self.db.query(CharacterSpellSlot).filter(
            CharacterSpellSlot.character_id == character_id
        ).update({CharacterSpellSlot.used: 0})
        self.db.commit()

    def get_known_spells(self, character_id: int) -> list[CharacterSpell]:
        return (
            self.db.query(CharacterSpell)
            .filter(CharacterSpell.character_id == character_id)
            .all()
        )

    def get_known_spell(self, character_id: int, spell_id: int) -> CharacterSpell | None:
        return (
            self.db.query(CharacterSpell)
            .filter(
                CharacterSpell.character_id == character_id,
                CharacterSpell.spell_id == spell_id,
            )
            .first()
        )

    def add_known_spell(self, character_id: int, spell_id: int) -> CharacterSpell:
        character_spell = CharacterSpell(
            character_id=character_id, spell_id=spell_id, is_prepared=False
        )
        self.db.add(character_spell)
        self.db.commit()
        self.db.refresh(character_spell)
        return character_spell

    def remove_known_spell(self, character_spell: CharacterSpell) -> bool:
        self.db.delete(character_spell)
        self.db.commit()
        return True

    def set_spell_prepared(
        self, character_spell: CharacterSpell, is_prepared: bool
    ) -> CharacterSpell:
        character_spell.is_prepared = is_prepared
        self.db.commit()
        self.db.refresh(character_spell)
        return character_spell