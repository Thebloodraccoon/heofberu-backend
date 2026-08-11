"""Class CRUD service including abilities/throws/skills/spell-slot/subclass management."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.cached_service import CachedService
from app.features.classes.exceptions import (
    InvalidClassLevelException,
    SpellcastingAbilityNotPrimaryException,
    SubclassNotFoundException,
)
from app.features.classes.repository import ClassRepository
from app.features.classes.schemas import (
    ArmorProficienciesUpdate,
    AvailableSkillsUpdate,
    ClassCreate,
    ClassGetAllResponse,
    ClassProgressionResponse,
    ClassResponse,
    ClassUpdate,
    ProgressionLevelRow,
    SavingThrowsUpdate,
    SpellSlotProgressionUpdate,
    SubclassBriefResponse,
    SubclassCreate,
    SubclassResponse,
    SubclassUpdate,
    _proficiency_bonus,
)
from app.features.features.mixins import SourceFeatureMixin
from app.features.features.nested_service import NestedFeatureService
from app.features.features.schemas import FeatureUpdate, NestedFeatureCreate, NestedFeatureResponse
from app.features.items.mixins import SourceItemManagerMixin
from app.features.items.nested_service import NestedSourceItemService
from app.features.skills.mixins import SkillsManagerMixin
from app.models.class_model import Class
from app.models.subclass_model import Subclass


class ClassService(
    SkillsManagerMixin,
    SourceFeatureMixin,
    SourceItemManagerMixin,
    CachedService[Class, ClassCreate, ClassUpdate, ClassResponse, ClassGetAllResponse],
):
    """
    Class-specific CRUD service built on :class:`CachedService`.

    Extends the generic base with:
      - name uniqueness check on create/update;
      - atomic creation of primary_abilities, saving_throws, armor
        proficiencies, available_skills, CLASS-source features,
        spell_slot_progression, and nested subclasses (each with their own
        SUBCLASS-source features) in a single transaction;
      - spellcasting_ability ↔ primary_abilities consistency checks;
      - subclass CRUD (create / get / list / update / delete), including
        per-subclass feature management via ``_mutate_feature`` and
        per-class/per-subclass feature listing (``list_features`` /
        ``list_subclass_features``);
      - per-class starting equipment (``list_items``/``set_items``) and
        nested ``starting_items`` on create, inherited from
        :class:`SourceItemManagerMixin`;
      - armor proficiency replacement (``set_armor_proficiencies``);
      - progression table builder (GET /classes/{id}/progression).

    Listing and detail reads are cached via ``@use_cache``. The class and
    subclass responses no longer embed their ``features`` — they are read
    through ``list_features`` / ``list_subclass_features`` (cached under
    the dedicated ``nested_features`` namespace), and starting equipment
    through ``list_items`` (cached under ``nested_items``), so the service
    invalidates its own namespace plus both nested namespaces on catalog
    writes.
    """

    repository: ClassRepository

    cache_namespaces = ("classes", "nested_features", "nested_items")

    _feature_source_type = FeatureSourceType.CLASS
    _source_item_source_type = FeatureSourceType.CLASS

    _set_skills_method = "set_available_skills"

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=ClassRepository(db),
            response_schema=ClassResponse,
            get_all_schema=ClassGetAllResponse,
        )
        self._features = NestedFeatureService(db)
        self._items = NestedSourceItemService(db)

    async def create_class(self, class_data: ClassCreate, created_by_id: int | None = None) -> ClassResponse:
        """
        Create a class and all nested sub-resources atomically.

        Within ``_atomic()``:
          1. Insert the ``Class`` row.
          2. Set primary_abilities, saving_throws, armor_proficiencies,
             available_skills.
          3. Create CLASS-source features.
          4. Apply spell_slot_progression.
          5. For each nested SubclassCreate: insert Subclass row, then
             create SUBCLASS-source features linked to the new subclass_id.
          6. Create CLASS-source starting items.

        Everything commits together or rolls back entirely.
        """

        skills = await self._resolve_skills(class_data.available_skills)

        payload = class_data.model_dump(
            exclude={
                "primary_abilities",
                "saving_throws",
                "armor_proficiencies",
                "available_skills",
                "features",
                "subclasses",
                "spell_slot_progression",
                "starting_items",
            }
        )
        payload["created_by_id"] = created_by_id

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

            if class_data.primary_abilities:
                await self.repository.set_primary_abilities(item, class_data.primary_abilities, commit=False)

            if class_data.saving_throws:
                await self.repository.set_saving_throws(item, class_data.saving_throws, commit=False)

            if class_data.armor_proficiencies:
                await self.repository.set_armor_proficiencies(item, class_data.armor_proficiencies, commit=False)

            if skills:
                await self.repository.set_available_skills(item, skills, commit=False)

            # CLASS-source features.
            await self._features.create_features_for_source(
                FeatureSourceType.CLASS,
                item.id,
                class_data.features,
                created_by_id,
                commit=False,
            )

            # CLASS-source starting items.
            await self._items.create_items_for_source(
                FeatureSourceType.CLASS,
                item.id,
                class_data.starting_items,
                commit=False,
            )

            # Spell slot progression.
            if class_data.spell_slot_progression:
                for entry in class_data.spell_slot_progression:
                    slots_by_spell_level = {slot.spell_level: slot.slots for slot in entry.slots}
                    await self.repository.set_spell_slots(item, entry.class_level, slots_by_spell_level, commit=False)

            # Nested subclasses + their SUBCLASS-source features.
            if class_data.subclasses:
                for sub_data in class_data.subclasses:
                    sub_payload = sub_data.model_dump(exclude={"features"})
                    sub_payload["created_by_id"] = created_by_id
                    subclass = await self.repository.create_subclass(item, sub_payload, commit=False)

                    await self._features.create_features_for_source(
                        FeatureSourceType.SUBCLASS,
                        subclass.id,
                        sub_data.features,
                        created_by_id,
                        commit=False,
                    )

        await self._invalidate_cache()

        return await self._get_response(item.id)

    async def update_class(self, class_id: int, update_data: ClassUpdate) -> ClassResponse:
        """
        Partially update a class (PATCH semantics).

        Checks spellcasting_ability ↔ primary_abilities consistency when
        primary_abilities is changed without an explicit spellcasting_ability.
        ``primary_abilities``/``saving_throws``/``armor_proficiencies`` are
        full-replace when set.
        """

        character_class = await self._get_or_404(class_id)
        fields = update_data.model_dump(
            exclude_unset=True, exclude={"primary_abilities", "saving_throws", "armor_proficiencies"}
        )

        if update_data.primary_abilities is not None and update_data.spellcasting_ability is None:
            current = character_class.spellcasting_ability
            if current is not None and current not in update_data.primary_abilities:
                raise SpellcastingAbilityNotPrimaryException(
                    spellcasting_ability=current,
                    primary_abilities=update_data.primary_abilities,
                )

        if fields:
            character_class = await self.repository.update(character_class, fields)

        if update_data.primary_abilities is not None:
            character_class = await self.repository.set_primary_abilities(
                character_class, update_data.primary_abilities
            )

        if update_data.saving_throws is not None:
            character_class = await self.repository.set_saving_throws(character_class, update_data.saving_throws)

        if update_data.armor_proficiencies is not None:
            character_class = await self.repository.set_armor_proficiencies(
                character_class, update_data.armor_proficiencies
            )

        await self._invalidate_cache()
        return await self._get_response(class_id)

    async def set_saving_throws(self, class_id: int, data: SavingThrowsUpdate) -> ClassResponse:
        character_class = await self._get_or_404(class_id)

        await self.repository.set_saving_throws(character_class, data.saving_throws)
        await self._invalidate_cache()

        return await self._get_response(class_id)

    async def set_armor_proficiencies(self, class_id: int, data: ArmorProficienciesUpdate) -> ClassResponse:
        character_class = await self._get_or_404(class_id)

        await self.repository.set_armor_proficiencies(character_class, data.armor_proficiencies)
        await self._invalidate_cache()

        return await self._get_response(class_id)

    async def set_available_skills(self, class_id: int, data: AvailableSkillsUpdate) -> ClassResponse:
        """Fully replace the skills a class may choose proficiencies from."""

        return await self.set_skills(class_id, data)

    async def set_spell_slots(self, class_id: int, class_level: int, data: SpellSlotProgressionUpdate) -> ClassResponse:
        """
        Replace spell slots for a single class_level.
        class_level must be 1-20 — checked here before touching the DB.
        """

        character_class = await self._get_or_404(class_id)
        if not (1 <= class_level <= 20):
            raise InvalidClassLevelException(class_level)

        slots_by_spell_level = {entry.spell_level: entry.slots for entry in data.slots}
        await self.repository.set_spell_slots(character_class, class_level, slots_by_spell_level)
        await self._invalidate_cache()

        return await self._get_response(class_id)

    async def create_subclass(
        self, class_id: int, data: SubclassCreate, created_by_id: int | None = None
    ) -> SubclassResponse:
        """
        Create a subclass (and its nested features) for an existing class.
        Uses ``_atomic()`` so the subclass row and its features commit together.
        """

        character_class = await self._get_or_404(class_id)

        sub_payload = data.model_dump(exclude={"features"})
        sub_payload["created_by_id"] = created_by_id

        async with self._atomic():
            subclass = await self.repository.create_subclass(character_class, sub_payload, commit=False)

            await self._features.create_features_for_source(
                FeatureSourceType.SUBCLASS,
                subclass.id,
                data.features,
                created_by_id,
                commit=False,
            )

        await self._invalidate_cache()

        return SubclassResponse.model_validate(await self._get_subclass_or_404(class_id, subclass.id))

    async def get_subclass(self, class_id: int, subclass_id: int) -> SubclassResponse:
        subclass = await self._get_subclass_or_404(class_id, subclass_id)

        return SubclassResponse.model_validate(subclass)

    async def list_subclasses(self, class_id: int) -> list[SubclassBriefResponse]:
        await self._get_or_404(class_id)  # 404 if class doesn't exist
        subclasses = await self.repository.list_subclasses(class_id)

        return [SubclassBriefResponse.model_validate(s) for s in subclasses]

    async def update_subclass(self, class_id: int, subclass_id: int, data: SubclassUpdate) -> SubclassResponse:
        subclass = await self._get_subclass_or_404(class_id, subclass_id)

        fields = data.model_dump(exclude_unset=True)
        await self.repository.update_subclass(subclass, fields)
        await self._invalidate_cache()

        return SubclassResponse.model_validate(await self._get_subclass_or_404(class_id, subclass_id))

    async def list_features(self, class_id: int) -> list[NestedFeatureResponse]:
        """Return every CLASS-source feature of the class (cached under ``nested_features``)."""

        await self._get_or_404(class_id)  # 404 if class doesn't exist
        return await self._features.list_for_source(FeatureSourceType.CLASS, class_id)

    async def list_subclass_features(self, class_id: int, subclass_id: int) -> list[NestedFeatureResponse]:
        """Return every SUBCLASS-source feature of the subclass (cached under ``nested_features``)."""

        subclass = await self._get_subclass_or_404(class_id, subclass_id)
        return await self._features.list_for_source(FeatureSourceType.SUBCLASS, subclass.id)

    async def add_subclass_feature(
        self,
        class_id: int,
        subclass_id: int,
        data: NestedFeatureCreate,
        created_by_id: int | None = None,
    ) -> NestedFeatureResponse:
        """
        Add one SUBCLASS-source feature to a subclass.

        Creates a new feature owned by the subclass, then reconciles the
        grants of every character holding this subclass so qualifying
        characters gain it in the same transaction. Returns the created
        feature.
        """

        subclass = await self._get_subclass_or_404(class_id, subclass_id)
        return await self._mutate_feature(
            subclass,
            FeatureSourceType.SUBCLASS,
            lambda: self._features.create_feature_for_source(
                FeatureSourceType.SUBCLASS,
                subclass.id,
                data,
                created_by_id,
                commit=False,
            ),
        )

    async def update_subclass_feature(
        self,
        class_id: int,
        subclass_id: int,
        feature_id: int,
        update_data: FeatureUpdate,
    ) -> NestedFeatureResponse:
        """
        Update one SUBCLASS-source feature of a subclass in place, keeping its id.

        The row keeps its id, so character grants and any player notes on
        them survive. Characters are reconciled in the same transaction —
        raising a feature's ``level`` revokes it from characters below the
        new level. Returns the updated feature.
        """

        subclass = await self._get_subclass_or_404(class_id, subclass_id)
        fields = update_data.model_dump(exclude_unset=True)
        return await self._mutate_feature(
            subclass,
            FeatureSourceType.SUBCLASS,
            lambda: self._features.update_feature_for_source(
                FeatureSourceType.SUBCLASS,
                subclass.id,
                feature_id,
                fields,
                commit=False,
            ),
        )

    async def remove_subclass_feature(self, class_id: int, subclass_id: int, feature_id: int) -> None:
        """
        Remove one SUBCLASS-source feature from a subclass.

        The feature row is deleted, cascading its ``character_features``
        grants away; characters are reconciled in the same transaction.
        """

        subclass = await self._get_subclass_or_404(class_id, subclass_id)
        await self._mutate_feature(
            subclass,
            FeatureSourceType.SUBCLASS,
            lambda: self._features.delete_feature_for_source(
                FeatureSourceType.SUBCLASS,
                subclass.id,
                feature_id,
                commit=False,
            ),
        )

    async def delete_subclass(self, class_id: int, subclass_id: int) -> None:
        subclass = await self._get_subclass_or_404(class_id, subclass_id)
        await self.repository.delete_subclass(subclass)

        await self._invalidate_cache()

    async def _get_subclass_or_404(self, class_id: int, subclass_id: int) -> Subclass:
        await self._get_or_404(class_id)  # 404 if class doesn't exist

        subclass = await self.repository.get_subclass(class_id, subclass_id)
        if not subclass:
            raise SubclassNotFoundException(class_id=class_id, subclass_id=subclass_id)

        return subclass

    async def get_progression(self, class_id: int) -> ClassProgressionResponse:
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
        character_class = await self._get_or_404(class_id)

        # Index spell slots by class_level → {spell_level: slots}
        slots_by_level: dict[int, dict[str, int]] = {}
        for row in character_class.spell_slot_progression:
            slots_by_level.setdefault(row.class_level, {})[row.spell_level] = row.slots

        # Fetch all CLASS + SUBCLASS features for this class, ordered by level.
        all_features = await self.repository.get_progression_features(class_id)

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
