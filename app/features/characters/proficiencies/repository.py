from sqlalchemy.orm import Session

from app.core.base_repository import BaseRepository
from app.models.character_association_models import (
    CharacterSavingThrowProficiency,
    CharacterSkillProficiency,
)
from app.models.character_model import Character


class CharacterProficiencyRepository(BaseRepository[CharacterSkillProficiency]):
    """
    Repository for a character's skill and saving-throw proficiencies.

    Split out of ``CharacterRepository`` — these are their own
    association tables (``character_skill_proficiencies``,
    ``character_saving_throw_proficiencies``), unrelated to the
    ``Character`` row's own columns. Bound to ``CharacterSkillProficiency``
    as its primary model since that's the more actively queried of the
    two; ``BaseRepository``'s generic CRUD isn't used directly here since
    both operations are full-replacement, not per-row create/update.
    """

    def __init__(self, db: Session):
        super().__init__(CharacterSkillProficiency, db)

    def get_skill_proficiency(self, character_id: int, skill_id: int) -> CharacterSkillProficiency | None:
        return (
            self.db.query(CharacterSkillProficiency)
            .filter(
                CharacterSkillProficiency.character_id == character_id,
                CharacterSkillProficiency.skill_id == skill_id,
            )
            .first()
        )

    def get_saving_throw_proficiency(self, character_id: int, ability: str) -> CharacterSavingThrowProficiency | None:
        return (
            self.db.query(CharacterSavingThrowProficiency)
            .filter(
                CharacterSavingThrowProficiency.character_id == character_id,
                CharacterSavingThrowProficiency.ability == ability,
            )
            .first()
        )

    def set_skill_proficiencies(self, character: Character, proficiencies: list[dict]) -> Character:
        """
        Replace all skill proficiencies for a character with the given list.

        Each item is expected to have 'skill_id' and 'is_expertise'.
        """

        self.db.query(CharacterSkillProficiency).filter(CharacterSkillProficiency.character_id == character.id).delete()

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

    def set_saving_throw_proficiencies(self, character: Character, abilities: list[str]) -> Character:
        """Replace all saving throw proficiencies for a character with the given list."""

        self.db.query(CharacterSavingThrowProficiency).filter(
            CharacterSavingThrowProficiency.character_id == character.id
        ).delete()

        for ability in abilities:
            self.db.add(CharacterSavingThrowProficiency(character_id=character.id, ability=ability))

        self.db.commit()
        self.db.refresh(character)
        return character
