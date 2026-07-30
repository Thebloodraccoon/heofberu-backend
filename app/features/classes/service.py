from sqlalchemy.orm import Session

from app.core.service import BaseService
from app.models.class_model import Class

from ..races.exceptions import InvalidSkillIdsException
from .exceptions import ClassNameAlreadyExistsException, ClassNotFoundException
from .repository import ClassRepository
from .schemas import AvailableSkillsUpdate, ClassCreate, ClassResponse, ClassUpdate, SavingThrowsUpdate


class ClassService(BaseService[Class, ClassCreate, ClassUpdate, ClassResponse]):
    """
    Class-specific CRUD service built on :class:`BaseService`.

    Adds behaviors the generic base class doesn't provide:
      - a plain, unpaginated ``get_all`` (classes are listed in full, sorted
        by name, via ``ClassRepository.get_all``);
      - a uniqueness check on ``name`` before create/update;
      - management of primary abilities, saving throws, and available
        skills, which live in their own association tables and have no
        generic base-class equivalent.
    """

    def __init__(self, db: Session):
        super().__init__(
            repository=ClassRepository(db),
            response_schema=ClassResponse,
            not_found_exception_factory=lambda class_id: ClassNotFoundException(class_id=class_id),
        )
        self.repository: ClassRepository

    def get_all_classes(self) -> list[ClassResponse]:
        """Return every class, ordered by name (no pagination)."""

        classes = self.repository.get_all()
        return [ClassResponse.model_validate(c) for c in classes]

    def get_class_by_id(self, class_id: int) -> ClassResponse:
        """Return a single class by ID, or raise ``ClassNotFoundException``."""

        return self.get_by_id(class_id)

    def create_class(self, class_data: ClassCreate) -> ClassResponse:
        """
        Create a class after checking its name isn't already taken.

        ``primary_abilities`` is stored in its own association table, so it's
        excluded from the base ``create`` call and applied separately.
        """
        self._check_name_available(class_data.name)

        fields = class_data.model_dump(exclude={"primary_abilities"})
        primary_abilities = class_data.primary_abilities

        character_class = self.repository.create(fields)
        character_class = self.repository.set_primary_abilities(character_class, primary_abilities)
        return self.response_schema.model_validate(character_class)

    def update_class(self, class_id: int, update_data: ClassUpdate) -> ClassResponse:
        """
        Update a class, re-checking name uniqueness if the name is changing.

        ``primary_abilities``, when provided, fully replaces the existing
        list via the repository rather than through the generic ``update``.
        """
        character_class = self._get_or_404(class_id)

        fields = update_data.model_dump(exclude_unset=True, exclude={"primary_abilities"})

        if "name" in fields and fields["name"] != character_class.name:
            self._check_name_available(fields["name"])

        if fields:
            character_class = self.repository.update(character_class, fields)

        if update_data.primary_abilities is not None:
            character_class = self.repository.set_primary_abilities(character_class, update_data.primary_abilities)

        return self.response_schema.model_validate(character_class)

    def delete_class(self, class_id: int) -> bool:
        """Delete a class by ID, or raise ``ClassNotFoundException``."""

        return self.delete(class_id)

    def set_saving_throws(self, class_id: int, data: SavingThrowsUpdate) -> ClassResponse:
        """Fully replace a class's saving throw proficiencies."""
        character_class = self._get_or_404(class_id)

        updated_class = self.repository.set_saving_throws(character_class, data.saving_throws)
        return self.response_schema.model_validate(updated_class)

    def set_available_skills(self, class_id: int, data: AvailableSkillsUpdate) -> ClassResponse:
        """Fully replace the skills a class may choose proficiencies from."""

        character_class = self._get_or_404(class_id)

        skills = self.repository.get_skills_by_ids(data.skill_ids)
        found_ids = {skill.id for skill in skills}
        missing_ids = [skill_id for skill_id in data.skill_ids if skill_id not in found_ids]
        if missing_ids:
            raise InvalidSkillIdsException(missing_ids)

        updated_class = self.repository.set_available_skills(character_class, skills)
        return self.response_schema.model_validate(updated_class)

    def _check_name_available(self, name: str) -> None:
        """Raise ``ClassNameAlreadyExistsException`` if ``name`` is already in use."""

        if self.repository.get_by_name(name):
            raise ClassNameAlreadyExistsException(name)
