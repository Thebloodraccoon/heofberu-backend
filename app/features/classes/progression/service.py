"""Class progression service: spell-slot table and the derived 1-20 progression."""

import math

from app.core.cache import use_cache
from app.core.exceptions import RecordNotFoundError
from app.features.classes.crud.schemas import ClassResponse
from app.features.classes.progression.schemas import (
    ClassProgressionResponse,
    ProgressionLevelRow,
    ProgressionSubclassFeature,
    SpellSlotProgressionUpdate,
)
from app.features.classes.service_base import ClassScopedService
from app.features.features.crud.schemas import NestedFeatureResponse

MIN_CLASS_LEVEL = 1
MAX_CLASS_LEVEL = 20


def _proficiency_bonus(class_level: int) -> int:
    """Return the proficiency bonus for a given class level (1-20)."""

    return math.ceil(class_level / 4) + 1


class ClassProgressionService(ClassScopedService):
    """
    A class's progression: ``set_spell_slots`` replaces one level's slot rows,
    ``get_progression`` builds the whole 1-20 table (cached under ``classes``,
    which every class, subclass and feature write purges).
    """

    async def set_spell_slots(self, class_id: int, class_level: int, data: SpellSlotProgressionUpdate) -> ClassResponse:
        """Replace the spell slots of a single ``class_level`` (the router bounds it to 1-20)."""

        await self._exists_or_404(class_id)

        slots_by_spell_level: dict[str, int] = {entry.spell_level: entry.slots for entry in data.slots}
        await self.repository.set_spell_slots(class_id, class_level, slots_by_spell_level)
        await self._invalidate_cache()

        return await self._get_response(class_id)

    @use_cache(namespace="classes")
    async def get_progression(self, class_id: int) -> ClassProgressionResponse:
        """Build the full 1-20 progression table for a class (slots + class/subclass features)."""

        class_name = await self.repository.get_name(class_id)
        if class_name is None:
            raise RecordNotFoundError(model_name="Class", model_id=str(class_id))

        slots_by_level: dict[int, dict[str, int]] = {}
        for row in await self.repository.get_spell_slot_rows(class_id):
            slots_by_level.setdefault(row.class_level, {})[row.spell_level] = row.slots

        class_features: dict[int, list] = {}
        subclass_features: dict[int, list] = {}
        for feature in await self.repository.get_progression_features(class_id):
            if feature.level is None:  # only levelled features appear on the 1-20 table
                continue
            bucket = class_features if feature.subclass_id is None else subclass_features
            bucket.setdefault(feature.level, []).append(feature)

        rows = [
            ProgressionLevelRow(
                level=level,
                proficiency_bonus=_proficiency_bonus(level),
                spell_slots=slots_by_level.get(level, {}),
                class_features=[NestedFeatureResponse.model_validate(f) for f in class_features.get(level, [])],
                subclass_features=[
                    ProgressionSubclassFeature.model_validate(f) for f in subclass_features.get(level, [])
                ],
            )
            for level in range(MIN_CLASS_LEVEL, MAX_CLASS_LEVEL + 1)
        ]

        return ClassProgressionResponse(class_id=class_id, class_name=class_name, rows=rows)
