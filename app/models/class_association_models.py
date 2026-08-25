"""ORM models/tables for class sub-resources: available skills, saving throws, armor/weapon proficiencies."""

from sqlalchemy import Column, ForeignKey, Integer, Table

from app.models.enums import AbilityScoreType, ArmorProficiencyType, WeaponProficiencyType
from app.settings import settings

# classes <-> skills (skills a class may choose proficiencies from)
class_available_skills = Table(
    "class_available_skills",
    settings.Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", Integer, ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True),
)


class ClassSavingThrow(settings.Base):  # type: ignore
    """Saving throw proficiencies granted by a class, e.g. Fighter -> STR, CON."""

    __tablename__ = "class_saving_throws"

    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True)
    ability = Column(AbilityScoreType, primary_key=True)

    def __repr__(self):
        return f"<ClassSavingThrow(class_id={self.class_id}, ability='{self.ability}')>"


class ClassArmorProficiency(settings.Base):  # type: ignore
    """Armor proficiencies granted by a class, e.g. Fighter -> LIGHT, MEDIUM, HEAVY, SHIELD."""

    __tablename__ = "class_armor_proficiencies"

    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True)
    armor_type = Column(ArmorProficiencyType, primary_key=True)

    def __repr__(self):
        return f"<ClassArmorProficiency(class_id={self.class_id}, armor_type='{self.armor_type}')>"


class ClassWeaponProficiency(settings.Base):  # type: ignore
    """Weapon proficiencies granted by a class, e.g. Fighter -> SIMPLE, MARTIAL."""

    __tablename__ = "class_weapon_proficiencies"

    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True)
    weapon_category = Column(WeaponProficiencyType, primary_key=True)

    def __repr__(self):
        return f"<ClassWeaponProficiency(class_id={self.class_id}, weapon_category='{self.weapon_category}')>"
