"""ORM model for the reference table of playable classes."""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, and_
from sqlalchemy.orm import relationship

from app.constants import FeatureSourceType
from app.models.class_association_models import class_available_skills
from app.models.enums import AbilityScoreType, DiceTypeColumn
from app.models.feature_model import Feature
from app.settings import settings


class Class(settings.Base):  # type: ignore
    """
    Reference table of playable classes (e.g. Fighter, Wizard), shared
    across all characters. GM-managed, like Race and Spell.
    """

    __tablename__ = "classes"

    id = Column(Integer, primary_key=True)

    name = Column(String(100), nullable=False, unique=True, index=True)
    hit_dice = Column(DiceTypeColumn, nullable=False)
    skill_choice_count = Column(Integer, nullable=False, default=2)
    spellcasting_ability = Column(AbilityScoreType, nullable=True)

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
    spell_slot_progression = relationship(
        "ClassSpellSlotProgression",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ClassSpellSlotProgression.class_level, ClassSpellSlotProgression.spell_level",
    )
    subclasses = relationship(
        "Subclass",
        back_populates="character_class",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Subclass.name",
    )
    # CLASS-source features granted by this class across all levels.
    # Subclass features are excluded from this relationship — they are
    # exposed through ``Subclass.features``.
    features = relationship(
        "Feature",
        viewonly=True,
        primaryjoin=lambda: and_(
            Feature.class_id == Class.id,
            Feature.source_type == FeatureSourceType.CLASS,
        ),
        order_by="Feature.level",
    )
    characters = relationship("Character", back_populates="character_class")
    created_by = relationship("User")

    def __repr__(self):
        return f"<Class(id={self.id}, name='{self.name}')>"
