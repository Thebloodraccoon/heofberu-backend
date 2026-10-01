"""ORM models/tables for class sub-resources: available skills, saving throws, armor/weapon proficiencies."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Index, Integer, Table
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import AbilityScore, ArmorProficiency, WeaponProficiency
from app.models.enums import AbilityScoreType, ArmorProficiencyType, WeaponProficiencyType
from app.settings.base import Base

class_available_skills = Table(
    "class_available_skills",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", Integer, ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True),
    # The composite PK is (class_id, skill_id) — a lone `WHERE skill_id = ...`
    # (e.g. the skill-deletion in-use guard) can't use it, hence this index.
    Index("ix_class_available_skills_skill_id", "skill_id"),
)


class ClassSavingThrow(Base):
    """Saving throw proficiencies granted by a class, e.g. Fighter -> STR, CON."""

    __tablename__ = "class_saving_throws"

    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True)
    ability: Mapped[AbilityScore] = mapped_column(AbilityScoreType, primary_key=True)

    def __repr__(self) -> str:
        return f"<ClassSavingThrow(class_id={self.class_id}, ability='{self.ability}')>"


class ClassArmorProficiency(Base):
    """Armor proficiencies granted by a class, e.g. Fighter -> LIGHT, MEDIUM, HEAVY, SHIELD."""

    __tablename__ = "class_armor_proficiencies"

    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True)
    armor_type: Mapped[ArmorProficiency] = mapped_column(ArmorProficiencyType, primary_key=True)

    def __repr__(self) -> str:
        return f"<ClassArmorProficiency(class_id={self.class_id}, armor_type='{self.armor_type}')>"


class ClassWeaponProficiency(Base):
    """Weapon proficiencies granted by a class, e.g. Fighter -> SIMPLE, MARTIAL."""

    __tablename__ = "class_weapon_proficiencies"

    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True)
    weapon_category: Mapped[WeaponProficiency] = mapped_column(WeaponProficiencyType, primary_key=True)

    def __repr__(self) -> str:
        return f"<ClassWeaponProficiency(class_id={self.class_id}, weapon_category='{self.weapon_category}')>"
