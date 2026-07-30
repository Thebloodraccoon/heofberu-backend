from sqlalchemy.orm import Session

from app.core.repository import BaseRepository
from app.models import Class, ClassPrimaryAbility, ClassSavingThrow, Skill


class ClassRepository(BaseRepository[Class]):
    def __init__(self, db: Session):
        super().__init__(Class, db)

    def get_all(self) -> list[Class]:
        """Get all classes, ordered by name (overrides base pagination-based get_all)."""
        return self.db.query(Class).order_by(Class.name).all()

    def get_by_name(self, name: str) -> Class | None:
        return self.db.query(Class).filter(Class.name == name).first()

    def set_primary_abilities(self, character_class: Class, abilities: list[str]) -> Class:
        """
        Replace all primary abilities for a class with the given list.

        Called internally from create/update — there is no dedicated PUT
        endpoint for this relationship.
        """
        self.db.query(ClassPrimaryAbility).filter(ClassPrimaryAbility.class_id == character_class.id).delete()

        for ability in abilities:
            self.db.add(ClassPrimaryAbility(class_id=character_class.id, ability=ability))

        self.db.commit()
        self.db.refresh(character_class)
        return character_class

    def set_saving_throws(self, character_class: Class, abilities: list[str]) -> Class:
        """Replace all saving throw proficiencies for a class with the given list."""
        self.db.query(ClassSavingThrow).filter(ClassSavingThrow.class_id == character_class.id).delete()

        for ability in abilities:
            self.db.add(ClassSavingThrow(class_id=character_class.id, ability=ability))

        self.db.commit()
        self.db.refresh(character_class)
        return character_class

    def get_skills_by_ids(self, skill_ids: list[int]) -> list[Skill]:
        if not skill_ids:
            return []
        return self.db.query(Skill).filter(Skill.id.in_(skill_ids)).all()

    def set_available_skills(self, character_class: Class, skills: list[Skill]) -> Class:
        """Replace all skills a class may choose proficiencies from."""
        character_class.available_skills = skills
        self.db.commit()
        self.db.refresh(character_class)
        return character_class
