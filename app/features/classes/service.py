"""Class CRUD service including abilities/throws/skills/spell-slot management."""

from sqlalchemy.orm import Session

from app.core.base_service import BaseService
from app.features.classes.exceptions import (
    InvalidClassLevelException,
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
    SpellSlotProgressionUpdate,
)
from app.models.class_model import Class


class ClassService(BaseService[Class, ClassCreate, ClassUpdate, ClassResponse, ClassBriefResponse]):
    """
    Class-specific CRUD service built on :class:`BaseService`.

    Adds behaviors the generic base class doesn't provide:
      - a uniqueness check on ``name`` before create/update;
      - management of primary abilities, saving throws, and available
        skills, which live in their own association tables and have no
        generic base-class equivalent. ``create_class`` sets all three up
        front, in the same transaction as the class itself (via
        ``BaseService._atomic``);
      - a consistency check tying ``spellcasting_ability`` to
        ``primary_abilities`` — see ``create_class`` and ``update_class``.

    ``get_all``, ``get_by_id``, and ``delete`` are inherited unchanged from
    ``BaseService``. ``delete``'s "still in use" guard (raising
    ``RecordInUseError`` if the class is still assigned to any character)
    lives in ``ClassRepository`` (``check_in_use_on_delete=True`` +
    ``is_in_use``), not here — see ``BaseRepository.delete``.
    """

    repository: ClassRepository

    def __init__(self, db: Session):
        super().__init__(
            repository=ClassRepository(db),
            response_schema=ClassResponse,
            brief_schema=ClassBriefResponse,
        )

    def create_class(self, class_data: ClassCreate, created_by_id: int | None = None) -> ClassResponse:
        """
        Create a class after checking its name isn't already taken.

        ``created_by_id`` identifies the GM who created it (relevant mainly
        for homebrew classes) and is not part of ``ClassCreate`` itself,
        since it comes from the authenticated user, not client input.

        ``primary_abilities``, ``saving_throws``, and ``available_skills``
        are stored in their own association tables and are set in the
        *same transaction* as the class itself (base fields + all three
        commit together, or none do), via ``self._atomic()``.
        ``available_skills`` is optional — a class can be created without
        granting any skill choices, same as Race's ``granted_skills``.

        The consistency check that ``spellcasting_ability`` (if set) is
        also in ``primary_abilities`` already ran in
        ``ClassCreate.validate_spellcasting_ability_is_primary`` at the
        schema layer, since both fields are always present together on a
        creation payload — no DB lookup needed there, unlike on update.
        """

        skills = (
            self.resolve_ids(self.repository.get_skills_by_ids, class_data.available_skills, "Skills")
            if class_data.available_skills
            else None
        )

        payload = class_data.model_dump(exclude={"primary_abilities", "saving_throws", "available_skills"})
        payload["created_by_id"] = created_by_id

        with self._atomic():
            item = self.repository.create(payload, commit=False)

            if class_data.primary_abilities:
                self.repository.set_primary_abilities(item, class_data.primary_abilities, commit=False)

            if class_data.saving_throws:
                self.repository.set_saving_throws(item, class_data.saving_throws, commit=False)

            if skills:
                self.repository.set_available_skills(item, skills, commit=False)

        self.repository.refresh(item)

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

    def set_saving_throws(self, class_id: int, data: SavingThrowsUpdate) -> ClassResponse:
        """Fully replace a class's saving throw proficiencies."""
        character_class = self._get_or_404(class_id)

        updated_class = self.repository.set_saving_throws(character_class, data.saving_throws)
        return self.response_schema.model_validate(updated_class)

    def set_available_skills(self, class_id: int, data: AvailableSkillsUpdate) -> ClassResponse:
        """Fully replace the skills a class may choose proficiencies from."""

        character_class = self._get_or_404(class_id)

        skills = self.resolve_ids(self.repository.get_skills_by_ids, data.skill_ids, "Skills")

        updated_class = self.repository.set_available_skills(character_class, skills)
        return self.response_schema.model_validate(updated_class)

    def set_spell_slots(self, class_id: int, class_level: int, data: SpellSlotProgressionUpdate) -> ClassResponse:
        """
        Replace the spell slots a class grants at a single ``class_level``.

        No check against ``spellcasting_ability`` is performed — a
        progression may be set for any class, caster or not, to support
        cases like multiclass slot tables. ``class_level`` must be within
        1-20 (matching the model's check constraint); anything outside
        that range is rejected before touching the database rather than
        relying on the DB to raise an ``IntegrityError``.
        """
        character_class = self._get_or_404(class_id)

        if not (1 <= class_level <= 20):
            raise InvalidClassLevelException(class_level)

        slots_by_spell_level = {entry.spell_level: entry.slots for entry in data.slots}

        updated_class = self.repository.set_spell_slots(character_class, class_level, slots_by_spell_level)
        return self.response_schema.model_validate(updated_class)
