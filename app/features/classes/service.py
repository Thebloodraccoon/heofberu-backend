from sqlalchemy.orm import Session

from app.exceptions.class_exceptions import (
    ClassNameAlreadyExistsException,
    ClassNotFoundException,
)
from app.exceptions.race_exceptions import InvalidSkillIdsException
from app.features.classes.repository import ClassRepository
from app.features.classes.schemas import (
    AvailableSkillsUpdate,
    ClassCreate,
    ClassResponse,
    ClassUpdate,
    SavingThrowsUpdate,
)


class ClassService:
    def __init__(self, db: Session):
        self.repository = ClassRepository(db)

    def get_all_classes(self) -> list[ClassResponse]:
        classes = self.repository.get_all()
        return [ClassResponse.model_validate(c) for c in classes]

    def get_class_by_id(self, class_id: int) -> ClassResponse:
        character_class = self._get_class_or_404(class_id)
        return ClassResponse.model_validate(character_class)

    def create_class(self, class_data: ClassCreate) -> ClassResponse:
        self._check_name_available(class_data.name)

        fields = class_data.model_dump(exclude={"primary_abilities"})
        primary_abilities = class_data.primary_abilities

        character_class = self.repository.create(fields)
        character_class = self.repository.set_primary_abilities(
            character_class, primary_abilities
        )
        return ClassResponse.model_validate(character_class)

    def update_class(self, class_id: int, update_data: ClassUpdate) -> ClassResponse:
        character_class = self._get_class_or_404(class_id)

        fields = update_data.model_dump(exclude_unset=True, exclude={"primary_abilities"})

        if "name" in fields and fields["name"] != character_class.name:
            self._check_name_available(fields["name"])

        if fields:
            character_class = self.repository.update(character_class, fields)

        if update_data.primary_abilities is not None:
            character_class = self.repository.set_primary_abilities(
                character_class, update_data.primary_abilities
            )

        return ClassResponse.model_validate(character_class)

    def delete_class(self, class_id: int) -> bool:
        character_class = self._get_class_or_404(class_id)
        return self.repository.delete(character_class)

    def set_saving_throws(self, class_id: int, data: SavingThrowsUpdate) -> ClassResponse:
        """Fully replace a class's saving throw proficiencies."""
        character_class = self._get_class_or_404(class_id)

        updated_class = self.repository.set_saving_throws(character_class, data.saving_throws)
        return ClassResponse.model_validate(updated_class)

    def set_available_skills(self, class_id: int, data: AvailableSkillsUpdate) -> ClassResponse:
        """Fully replace the skills a class may choose proficiencies from."""
        character_class = self._get_class_or_404(class_id)

        skills = self.repository.get_skills_by_ids(data.skill_ids)
        found_ids = {skill.id for skill in skills}
        missing_ids = [skill_id for skill_id in data.skill_ids if skill_id not in found_ids]
        if missing_ids:
            raise InvalidSkillIdsException(missing_ids)

        updated_class = self.repository.set_available_skills(character_class, skills)
        return ClassResponse.model_validate(updated_class)

    def _get_class_or_404(self, class_id: int):
        character_class = self.repository.get_by_id(class_id)
        if not character_class:
            raise ClassNotFoundException(class_id=class_id)
        return character_class

    def _check_name_available(self, name: str) -> None:
        if self.repository.get_by_name(name):
            raise ClassNameAlreadyExistsException(name)
