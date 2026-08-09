"""Class CRUD service including abilities/throws/skills/spell-slot/subclass management."""

from sqlalchemy.orm import Session

from app.constants import FeatureSourceType
from app.core.base_service import BaseService
from app.features.characters.progression.feature_sync import reconcile_characters_for_source
from app.features.classes.exceptions import (
    InvalidClassLevelException,
    SpellcastingAbilityNotPrimaryException,
    SubclassNotFoundException,
)
from app.features.classes.repository import ClassRepository
from app.features.classes.schemas import (
    AvailableSkillsUpdate,
    ClassBriefResponse,
    ClassCreate,
    ClassProgressionResponse,
    ClassResponse,
    ClassUpdate,
    NestedFeatureCreate,
    ProgressionLevelRow,
    SavingThrowsUpdate,
    SpellSlotProgressionUpdate,
    SubclassBriefResponse,
    SubclassCreate,
    SubclassResponse,
    SubclassUpdate,
    _proficiency_bonus,
)
from app.features.features.schemas import FeaturesReplace
from app.features.features.service import create_features_for_source, replace_features_for_source
from app.models.class_model import Class
from app.models.subclass_model import Subclass


class ClassService(BaseService[Class, ClassCreate, ClassUpdate, ClassResponse, ClassBriefResponse]):
    """
    Class-specific CRUD service built on :class:`BaseService`.

    Extends the generic base with:
      - name uniqueness check on create/update;
      - atomic creation of primary_abilities, saving_throws, available_skills,
        CLASS-source features, spell_slot_progression, and nested subclasses
        (each with their own SUBCLASS-source features) in a single transaction;
      - spellcasting_ability ↔ primary_abilities consistency checks;
      - subclass CRUD (create / get / list / update / delete);
      - progression table builder (GET /classes/{id}/progression).
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
        Create a class and all nested sub-resources atomically.

        Within ``_atomic()``:
          1. Insert the ``Class`` row.
          2. Set primary_abilities, saving_throws, available_skills.
          3. Create CLASS-source features.
          4. Apply spell_slot_progression.
          5. For each nested SubclassCreate: insert Subclass row, then
             create SUBCLASS-source features linked to the new subclass_id.

        Everything commits together or rolls back entirely.
        """
        skills = (
            self.resolve_ids(self.repository.get_skills_by_ids, class_data.available_skills, "Skills")
            if class_data.available_skills
            else None
        )

        payload = class_data.model_dump(
            exclude={
                "primary_abilities",
                "saving_throws",
                "available_skills",
                "features",
                "subclasses",
                "spell_slot_progression",
            }
        )
        payload["created_by_id"] = created_by_id

        with self._atomic():
            item = self.repository.create(payload, commit=False)

            if class_data.primary_abilities:
                self.repository.set_primary_abilities(item, class_data.primary_abilities, commit=False)

            if class_data.saving_throws:
                self.repository.set_saving_throws(item, class_data.saving_throws, commit=False)

            if skills:
                self.repository.set_available_skills(item, skills, commit=False)

            # CLASS-source features.
            create_features_for_source(
                self.repository.db,
                FeatureSourceType.CLASS,
                item.id,
                class_data.features,
                created_by_id,
                commit=False,
            )

            # Spell slot progression.
            if class_data.spell_slot_progression:
                for entry in class_data.spell_slot_progression:
                    slots_by_spell_level = {slot.spell_level: slot.slots for slot in entry.slots}
                    self.repository.set_spell_slots(item, entry.class_level, slots_by_spell_level, commit=False)

            # Nested subclasses + their SUBCLASS-source features.
            if class_data.subclasses:
                for sub_data in class_data.subclasses:
                    sub_payload = sub_data.model_dump(exclude={"features"})
                    sub_payload["created_by_id"] = created_by_id
                    subclass = self.repository.create_subclass(item, sub_payload, commit=False)

                    create_features_for_source(
                        self.repository.db,
                        FeatureSourceType.SUBCLASS,
                        subclass.id,
                        sub_data.features,
                        created_by_id,
                        commit=False,
                    )

        self.repository.refresh(item)
        return self.response_schema.model_validate(item)

    def update_class(self, class_id: int, update_data: ClassUpdate) -> ClassResponse:
        """
        Partially update a class (PATCH semantics).

        Checks spellcasting_ability ↔ primary_abilities consistency when
        primary_abilities is changed without an explicit spellcasting_ability.
        """
        character_class = self._get_or_404(class_id)
        fields = update_data.model_dump(exclude_unset=True, exclude={"primary_abilities", "saving_throws"})

        if update_data.primary_abilities is not None and update_data.spellcasting_ability is None:
            current = character_class.spellcasting_ability
            if current is not None and current not in update_data.primary_abilities:
                raise SpellcastingAbilityNotPrimaryException(
                    spellcasting_ability=current,
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
        character_class = self._get_or_404(class_id)
        updated = self.repository.set_saving_throws(character_class, data.saving_throws)
        return self.response_schema.model_validate(updated)

    def set_available_skills(self, class_id: int, data: AvailableSkillsUpdate) -> ClassResponse:
        character_class = self._get_or_404(class_id)
        skills = self.resolve_ids(self.repository.get_skills_by_ids, data.skill_ids, "Skills")
        updated = self.repository.set_available_skills(character_class, skills)
        return self.response_schema.model_validate(updated)

    def set_spell_slots(self, class_id: int, class_level: int, data: SpellSlotProgressionUpdate) -> ClassResponse:
        """
        Replace spell slots for a single class_level.
        class_level must be 1-20 — checked here before touching the DB.
        """
        character_class = self._get_or_404(class_id)
        if not (1 <= class_level <= 20):
            raise InvalidClassLevelException(class_level)
        slots_by_spell_level = {entry.spell_level: entry.slots for entry in data.slots}
        updated = self.repository.set_spell_slots(character_class, class_level, slots_by_spell_level)
        return self.response_schema.model_validate(updated)

    def replace_class_features(
        self, class_id: int, data: FeaturesReplace, created_by_id: int | None = None
    ) -> ClassResponse:
        """
        Full-replace a class's CLASS-source features, matched by feature id.

        Items carrying an ``id`` update that feature in place — the id is
        kept, so character grants and any player notes on them survive.
        Items without an ``id`` create new features; existing features
        whose id is absent from the payload are deleted, cascading their
        grants away. Runs atomically, then reconciles the grants of every
        character of this class so their builds match the new feature set.
        """
        character_class = self._get_or_404(class_id)
        with self._atomic():
            replace_features_for_source(
                self.repository.db,
                FeatureSourceType.CLASS,
                character_class.id,
                data.features,
                created_by_id,
                commit=False,
            )
            reconcile_characters_for_source(self.repository.db, FeatureSourceType.CLASS, character_class.id)
        self.repository.refresh(character_class)
        return self.response_schema.model_validate(character_class)

    def create_subclass(
        self, class_id: int, data: SubclassCreate, created_by_id: int | None = None
    ) -> SubclassResponse:
        """
        Create a subclass (and its nested features) for an existing class.
        Uses ``_atomic()`` so the subclass row and its features commit together.
        """
        character_class = self._get_or_404(class_id)

        sub_payload = data.model_dump(exclude={"features"})
        sub_payload["created_by_id"] = created_by_id

        with self._atomic():
            subclass = self.repository.create_subclass(character_class, sub_payload, commit=False)

            create_features_for_source(
                self.repository.db,
                FeatureSourceType.SUBCLASS,
                subclass.id,
                data.features,
                created_by_id,
                commit=False,
            )

        self.repository.db.refresh(subclass)
        return SubclassResponse.model_validate(subclass)

    def get_subclass(self, class_id: int, subclass_id: int) -> SubclassResponse:
        subclass = self._get_subclass_or_404(class_id, subclass_id)
        return SubclassResponse.model_validate(subclass)

    def list_subclasses(self, class_id: int) -> list[SubclassBriefResponse]:
        self._get_or_404(class_id)  # 404 if class doesn't exist
        subclasses = self.repository.list_subclasses(class_id)
        return [SubclassBriefResponse.model_validate(s) for s in subclasses]

    def update_subclass(self, class_id: int, subclass_id: int, data: SubclassUpdate) -> SubclassResponse:
        subclass = self._get_subclass_or_404(class_id, subclass_id)
        fields = data.model_dump(exclude_unset=True)
        updated = self.repository.update_subclass(subclass, fields)
        return SubclassResponse.model_validate(updated)

    def replace_subclass_features(
        self, class_id: int, subclass_id: int, data: FeaturesReplace, created_by_id: int | None = None
    ) -> SubclassResponse:
        """
        Full-replace a subclass's SUBCLASS-source features, matched by id.

        Same semantics as :meth:`replace_class_features` — items with an
        ``id`` keep that feature id (character grants survive), items
        without an ``id`` are created, and features absent from the payload
        are deleted. Grants of every character holding this subclass are
        reconciled to the new feature set in the same transaction.
        """
        subclass = self._get_subclass_or_404(class_id, subclass_id)
        with self._atomic():
            replace_features_for_source(
                self.repository.db,
                FeatureSourceType.SUBCLASS,
                subclass.id,
                data.features,
                created_by_id,
                commit=False,
            )
            reconcile_characters_for_source(self.repository.db, FeatureSourceType.SUBCLASS, subclass.id)
        self.repository.db.refresh(subclass)
        return SubclassResponse.model_validate(subclass)

    def delete_subclass(self, class_id: int, subclass_id: int) -> None:
        subclass = self._get_subclass_or_404(class_id, subclass_id)
        self.repository.delete_subclass(subclass)

    def _get_subclass_or_404(self, class_id: int, subclass_id: int) -> Subclass:
        self._get_or_404(class_id)  # 404 if class doesn't exist
        subclass = self.repository.get_subclass(class_id, subclass_id)
        if not subclass:
            raise SubclassNotFoundException(class_id=class_id, subclass_id=subclass_id)
        return subclass

    def get_progression(self, class_id: int) -> ClassProgressionResponse:
        """
        Build the full 1-20 progression table for a class.

        Each row contains:
          - level + proficiency_bonus (computed via ceil(level/4)+1)
          - spell_slots: {spell_level → slots} from ClassSpellSlotProgression
          - class_features: CLASS-source features gained at this level
          - subclass_features: SUBCLASS-source features gained at this level
            (across all subclasses — useful for showing "at level N you gain
             a subclass feature" without enumerating every subclass)
        """
        character_class = self._get_or_404(class_id)

        # Index spell slots by class_level → {spell_level: slots}
        slots_by_level: dict[int, dict[str, int]] = {}
        for row in character_class.spell_slot_progression:
            slots_by_level.setdefault(row.class_level, {})[row.spell_level] = row.slots

        # Fetch all CLASS + SUBCLASS features for this class, ordered by level.
        all_features = self.repository.get_progression_features(class_id)

        # Index features by (level, source_type)
        class_features_by_level: dict[int, list] = {}
        subclass_features_by_level: dict[int, list] = {}
        for f in all_features:
            lvl = f.level or 0
            if f.subclass_id is not None:
                subclass_features_by_level.setdefault(lvl, []).append(f)
            else:
                class_features_by_level.setdefault(lvl, []).append(f)

        rows = []
        for lvl in range(1, 21):
            rows.append(
                ProgressionLevelRow(
                    level=lvl,
                    proficiency_bonus=_proficiency_bonus(lvl),
                    spell_slots=slots_by_level.get(lvl, {}),
                    class_features=[
                        NestedFeatureCreate.model_validate(f) for f in class_features_by_level.get(lvl, [])
                    ],
                    subclass_features=[
                        NestedFeatureCreate.model_validate(f) for f in subclass_features_by_level.get(lvl, [])
                    ],
                )
            )

        return ClassProgressionResponse(
            class_id=class_id,
            class_name=character_class.name,
            rows=rows,
        )
