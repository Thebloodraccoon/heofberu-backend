from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.base_service import BaseService
from app.features.classes.exceptions import (
    ClassInUseException,
    ClassNameAlreadyExistsException,
    ClassNotFoundException,
    InvalidSkillIdsException,
    SpellcastingAbilityNotPrimaryException,
)
from app.features.classes.repository import ClassRepository
from app.features.classes.schemas import (
    AvailableSkillsUpdate,
    ClassBriefResponse,
    ClassCreate,
    ClassResponse,
    ClassUpdate,
    SavingThrowsUpdate,
)
from app.models.class_model import Class


class ClassService(BaseService[Class, ClassCreate, ClassUpdate, ClassResponse, ClassBriefResponse]):
    """
    Class-specific CRUD service built on :class:`BaseService`.

    Adds behaviors the generic base class doesn't provide:
      - a plain, unpaginated ``get_all`` (classes are listed in full, sorted
        by name, via ``ClassRepository.get_all``) — overridden here on the
        *service* too, not just the repository, so the public contract
        (no ``skip``/``limit``) is explicit rather than silently breaking
        callers that assume ``BaseService``'s paginated signature;
      - a uniqueness check on ``name`` before create/update;
      - management of primary abilities, saving throws, and available
        skills, which live in their own association tables and have no
        generic base-class equivalent. ``create_class`` sets all three up
        front, in the same transaction as the class itself;
      - a delete guard that blocks removing a class still assigned to any
        character, since the FK is ``ON DELETE RESTRICT``;
      - a consistency check tying ``spellcasting_ability`` to
        ``primary_abilities`` — see ``create_class`` and ``update_class``.
    """

    repository: ClassRepository

    def __init__(self, db: Session):
        super().__init__(
            repository=ClassRepository(db),
            response_schema=ClassResponse,
            not_found_exception_factory=lambda class_id: ClassNotFoundException(class_id=class_id),
            brief_schema=ClassBriefResponse,
        )
        self.db = db

    def create_class(self, class_data: ClassCreate, created_by_id: int | None = None) -> ClassResponse:
        """
        Create a class after checking its name isn't already taken.

        ``created_by_id`` identifies the GM who created it (relevant mainly
        for homebrew classes) and is not part of ``ClassCreate`` itself,
        since it comes from the authenticated user, not client input.

        ``primary_abilities``, ``saving_throws``, and ``available_skills``
        are stored in their own association tables and are set in the
        *same transaction* as the class itself (base fields + all three
        commit together, or none do). ``available_skills`` is optional —
        a class can be created without granting any skill choices, same
        as Race's ``granted_skills``.

        The consistency check that ``spellcasting_ability`` (if set) is
        also in ``primary_abilities`` already ran in
        ``ClassCreate.validate_spellcasting_ability_is_primary`` at the
        schema layer, since both fields are always present together on a
        create payload — no DB lookup needed there, unlike on update.

        Every write inside the nested transaction below passes
        ``commit=False`` — including ``repository.create`` itself. A plain
        ``session.commit()`` from any of them would commit (and close) the
        *entire* outer transaction, not just the ``begin_nested()``
        SAVEPOINT, breaking the context manager on exit. Only the final
        ``self.db.commit()`` after the ``with`` block should ever fire.
        """

        self._check_name_available(class_data.name)

        skills = None
        if class_data.available_skills:
            skills, missing_ids = self._resolve_skill_ids(class_data.available_skills)
            if missing_ids:
                raise InvalidSkillIdsException(missing_ids)

        payload = class_data.model_dump(exclude={"primary_abilities", "saving_throws", "available_skills"})
        payload["created_by_id"] = created_by_id

        try:
            with self.db.begin_nested():
                item = self.repository.create(payload, commit=False)

                if class_data.primary_abilities:
                    self.repository.set_primary_abilities(item, class_data.primary_abilities, commit=False)

                if class_data.saving_throws:
                    self.repository.set_saving_throws(item, class_data.saving_throws, commit=False)

                if skills:
                    self.repository.set_available_skills(item, skills, commit=False)

            self.db.commit()
            self.db.refresh(item)
        except Exception:
            self.db.rollback()
            raise

        return self.response_schema.model_validate(item)

    def update_class(self, class_id: int, update_data: ClassUpdate) -> ClassResponse:
        """
        Update a class, re-checking name uniqueness if the name is changing.

        ``primary_abilities`` and ``saving_throws`` are excluded from the
        base-field update and applied afterward via the repository, since
        they live in their own association tables and PATCH's "only touch
        what's set" doesn't map onto the generic ``BaseService.update``
        (which dumps the whole schema as flat fields) -- same rationale as
        ``RaceUpdate`` keeping ability_bonuses/granted_skills on their own
        PUT endpoints.

        Consistency check between ``spellcasting_ability`` and
        ``primary_abilities``: if the request changes ``primary_abilities``
        but does not also pass ``spellcasting_ability``, the class's
        *current* ``spellcasting_ability`` (if any) must still be a member
        of the new ``primary_abilities`` list — otherwise the update is
        rejected with ``SpellcastingAbilityNotPrimaryException``. This is
        the one case ``ClassUpdate``'s schema-level validator can't catch,
        since it needs the class's existing DB state, not just the request
        body. (The case where both fields ARE passed together is already
        validated at the schema layer.)
        """
        character_class = self._get_or_404(class_id)

        fields = update_data.model_dump(exclude_unset=True, exclude={"primary_abilities", "saving_throws"})

        if "name" in fields and fields["name"] != character_class.name:
            self._check_name_available(fields["name"])

        if update_data.primary_abilities is not None and update_data.spellcasting_ability is None:
            current_spellcasting_ability = character_class.spellcasting_ability
            if (
                current_spellcasting_ability is not None
                and current_spellcasting_ability not in update_data.primary_abilities
            ):
                raise SpellcastingAbilityNotPrimaryException(
                    spellcasting_ability=current_spellcasting_ability,
                    primary_abilities=update_data.primary_abilities,
                )

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

        skills, missing_ids = self._resolve_skill_ids(data.skill_ids)
        if missing_ids:
            raise InvalidSkillIdsException(missing_ids)

        updated_class = self.repository.set_available_skills(character_class, skills)
        return self.response_schema.model_validate(updated_class)

    def _check_name_available(self, name: str) -> None:
        """Raise ``ClassNameAlreadyExistsException`` if ``name`` is already in use."""

        if self.repository.get_by_name(name):
            raise ClassNameAlreadyExistsException(name)

    def _resolve_skill_ids(self, skill_ids: list[int]):
        """Look up skills by id, returning (found_skills, missing_ids)."""

        skills = self.repository.get_skills_by_ids(skill_ids)
        found_ids = {skill.id for skill in skills}
        missing_ids = [skill_id for skill_id in skill_ids if skill_id not in found_ids]
        return skills, missing_ids