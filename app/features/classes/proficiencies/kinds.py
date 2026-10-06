"""Descriptors of the class proficiency lists that are replaced as a whole (saving throws, armor, weapons)."""

from dataclasses import dataclass

from app.models import ClassArmorProficiency, ClassSavingThrow, ClassWeaponProficiency


@dataclass(frozen=True)
class ProficiencyKind:
    """One full-replace proficiency list: its request/response field and the child table behind it."""

    field: str
    model: type
    column: str


SAVING_THROWS = ProficiencyKind("saving_throws", ClassSavingThrow, "ability")
ARMOR_PROFICIENCIES = ProficiencyKind("armor_proficiencies", ClassArmorProficiency, "armor_type")
WEAPON_PROFICIENCIES = ProficiencyKind("weapon_proficiencies", ClassWeaponProficiency, "weapon_category")
