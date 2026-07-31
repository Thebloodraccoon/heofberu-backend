from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.class_association_models import class_available_skills
from app.models.enums import AbilityScoreType, DiceTypeColumn
from app.settings import settings


class Class(settings.Base):  # type: ignore
    """
    Reference table of playable classes (e.g. Fighter, Wizard), shared
    across all characters. GM-managed, like Race and Spell.
    """

    __tablename__ = "classes"

    id = Column(Integer, primary_key=True)

    name = Column(String(100), nullable=False, unique=True, index=True)
    hit_dice = Column(DiceTypeColumn, nullable=False)  # e.g. "1d10"
    skill_choice_count = Column(Integer, nullable=False, default=2)
    spellcasting_ability = Column(AbilityScoreType, nullable=True)  # NULL if non-caster

    description = Column(Text, nullable=False, default="")
    is_homebrew = Column(Boolean, nullable=False, default=False)

    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    primary_abilities = relationship(
        "ClassPrimaryAbility",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    saving_throws = relationship(
        "ClassSavingThrow",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    available_skills = relationship(
        "Skill",
        secondary=class_available_skills,
    )
    characters = relationship("Character", back_populates="character_class")
    created_by = relationship("User")

    def __repr__(self):
        return f"<Class(id={self.id}, name='{self.name}')>"
