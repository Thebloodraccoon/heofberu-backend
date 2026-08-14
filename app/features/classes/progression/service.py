"""Class progression service: spell-slot table and full 1-20 progression."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.classes.cache import CLASS_CACHE_NAMESPACES, invalidate_class_cache
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.exceptions import InvalidClassLevelException
from app.features.classes.schemas import (
    ClassCreate,
    ClassProgressionResponse,
    ClassResponse,
    ClassUpdate,
    ProgressionLevelRow,
    SpellSlotProgressionUpdate,
    _proficiency_bonus,
)
from app.features.shared.features.schemas import NestedFeatureCreate
from app.models.class_model import Class


class ClassProgressionService(BaseService[Class, ClassCreate, ClassUpdate, ClassResponse, None]):
    """
    Everything about a class's progression: the per-level spell-slot table
    and the full 1-20 progression table.

    ``set_spell_slots`` validates ``class_level`` (1-20) before touching
    the DB and full-replaces that level's rows. ``get_progression`` builds
    the whole 1-20 table straight from the eager-loaded
    ``spell_slot_progression`` and ``ClassRepository.get_progression_features``.
    Any write purges the ``classes``, ``nested_features`` and
    ``nested_items`` namespaces.
    """

    repository: ClassRepository

    cache_namespaces = CLASS_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=ClassRepository(db),
            response_schema=ClassResponse,
        )

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
        await invalidate_class_cache()

        return await self._get_response(class_id)

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
