from sqlalchemy import Column, ForeignKey, Integer, Table

from app.models.enums import AbilityScoreType
from app.settings import settings

# classes <-> skills (skills a class may choose proficiencies from)
class_available_skills = Table(
    "class_available_skills",
    settings.Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", Integer, ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True),
)


class ClassPrimaryAbility(settings.Base):  # type: ignore
    """Primary ability score(s) for a class, e.g. Fighter -> STR, Monk -> STR + DEX."""

    __tablename__ = "class_primary_abilities"

    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True)
    ability = Column(AbilityScoreType, primary_key=True)

    def __repr__(self):
        return f"<ClassPrimaryAbility(class_id={self.class_id}, ability='{self.ability}')>"


class ClassSavingThrow(settings.Base):  # type: ignore
    """Saving throw proficiencies granted by a class, e.g. Fighter -> STR, CON."""

    __tablename__ = "class_saving_throws"

    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True)
    ability = Column(AbilityScoreType, primary_key=True)

    def __repr__(self):
        return f"<ClassSavingThrow(class_id={self.class_id}, ability='{self.ability}')>"
