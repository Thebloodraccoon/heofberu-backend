from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.service import BaseService
from app.models.class_model import Class

from ..races.exceptions import InvalidSkillIdsException
from .exceptions import ClassInUseException, ClassNameAlreadyExistsException, ClassNotFoundException
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
        generic base-class equivalent;
      - a delete guard that blocks removing a class still assigned to any
        character, since the FK is ``ON DELETE RESTRICT``.
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

    def create_class(self, class_data: ClassCreate, created_by_id: int | None = None) -> ClassResponse:
        """
        Create a class after checking its name isn't already taken.

        ``primary_abilities`` and ``saving_throws`` are stored in their own
        association tables, so they're excluded from the base ``create``
        call and applied separately. ``created_by_id`` identifies the GM
        who created it (relevant mainly for homebrew classes) and is not
        part of ``ClassCreate`` itself, since it comes from the
        authenticated user, not client input.
        """
        self._check_name_available(class_data.name)

        fields = class_data.model_dump(exclude={"primary_abilities", "saving_throws"})
        fields["created_by_id"] = created_by_id
        primary_abilities = class_data.primary_abilities
        saving_throws = class_data.saving_throws

        character_class = self.repository.create(fields)
        character_class = self.repository.set_primary_abilities(character_class, primary_abilities)
        character_class = self.repository.set_saving_throws(character_class, saving_throws)
        return self.response_schema.model_validate(character_class)

    def update_class(self, class_id: int, update_data: ClassUpdate) -> ClassResponse:
        """
        Update a class, re-checking name uniqueness if the name is changing.

        ``primary_abilities`` and ``saving_throws``, when provided, fully
        replace the existing list via the repository rather than through
        the generic ``update``.
        """
        character_class = self._get_or_404(class_id)

        fields = update_data.model_dump(exclude_unset=True, exclude={"primary_abilities", "saving_throws"})

        if "name" in fields and fields["name"] != character_class.name:
            self._check_name_available(fields["name"])

        if fields:
            character_class = self.repository.update(character_class, fields)

        if update_data.primary_abilities is not None:
            character_class = self.repository.set_primary_abilities(character_class, update_data.primary_abilities)

        if update_data.saving_throws is not None:
            character_class = self.repository.set_saving_throws(character_class, update_data.saving_throws)

        return self.response_schema.model_validate(character_class)

    def delete_class(self, class_id: int) -> bool:
        """
        Delete a class by ID, raising ``ClassInUseException`` if it's still
        assigned to any character.

        Raises the feature's not-found exception if ``class_id`` doesn't
        exist. The in-use check happens before deletion, with an
        ``IntegrityError`` safety net in case of a race condition between
        the check and the actual delete (the FK is ``ON DELETE RESTRICT``).
        """
        character_class = self._get_or_404(class_id)

        if self.repository.is_in_use(class_id):
            raise ClassInUseException(class_id=class_id)

        try:
            return self.repository.delete(character_class)
        except IntegrityError:
            self.repository.db.rollback()
            raise ClassInUseException(class_id=class_id)

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
