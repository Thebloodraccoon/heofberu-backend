"""Class proficiency lists (saving throws, armor, weapons): one generic full-replace service."""

from app.features.classes.crud.schemas import ClassResponse
from app.features.classes.proficiencies.kinds import (
    ARMOR_PROFICIENCIES,
    SAVING_THROWS,
    WEAPON_PROFICIENCIES,
    ProficiencyKind,
)
from app.features.classes.proficiencies.schemas import (
    ArmorProficienciesUpdate,
    SavingThrowsUpdate,
    WeaponProficienciesUpdate,
)
from app.features.classes.service_base import ClassScopedService


class ClassProficiencyService(ClassScopedService):
    """Full replacement of a class's saving throws, armor proficiencies and weapon proficiencies."""

    async def replace(self, class_id: int, kind: ProficiencyKind, values: list) -> ClassResponse:
        """Replace the ``kind`` list of the class with ``values`` and return the updated class."""

        await self._exists_or_404(class_id)
        await self.repository.set_proficiencies(class_id, kind, values)
        await self._invalidate_cache()

        return await self._get_response(class_id)

    async def set_saving_throws(self, class_id: int, data: SavingThrowsUpdate) -> ClassResponse:
        """Fully replace a class's saving throw proficiencies."""

        return await self.replace(class_id, SAVING_THROWS, data.saving_throws)

    async def set_armor_proficiencies(self, class_id: int, data: ArmorProficienciesUpdate) -> ClassResponse:
        """Fully replace a class's armor proficiencies."""

        return await self.replace(class_id, ARMOR_PROFICIENCIES, data.armor_proficiencies)

    async def set_weapon_proficiencies(self, class_id: int, data: WeaponProficienciesUpdate) -> ClassResponse:
        """Fully replace a class's weapon proficiencies."""

        return await self.replace(class_id, WEAPON_PROFICIENCIES, data.weapon_proficiencies)
