"""ORM model for the reference table of playable classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Text, and_
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import AbilityScore, DiceType, FeatureSourceType
from app.models.classes.class_association_models import class_available_skills
from app.models.enums import AbilityScoreType, DiceTypeColumn
from app.models.features.feature_model import Feature
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.character.character_model import Character
    from app.models.classes.class_association_models import (
        ClassArmorProficiency,
        ClassSavingThrow,
        ClassWeaponProficiency,
    )
    from app.models.classes.class_spell_slot_progression_model import ClassSpellSlotProgression
    from app.models.classes.subclass_model import Subclass
    from app.models.items.item_source_choice_model import SourceItemChoiceGroup
    from app.models.items.item_source_model import SourceItem
    from app.models.skill_model import Skill


class Class(Base):
    """
    Reference table of playable classes (e.g. Fighter, Wizard), shared
    across all characters. GM-managed, like Race and Spell.
    """

    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    hit_dice: Mapped[DiceType] = mapped_column(DiceTypeColumn)
    skill_choice_count: Mapped[int] = mapped_column(default=2)
    spellcasting_ability: Mapped[AbilityScore | None] = mapped_column(AbilityScoreType)

    description: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str | None] = mapped_column(String(512))

    saving_throws: Mapped[list[ClassSavingThrow]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    armor_proficiencies: Mapped[list[ClassArmorProficiency]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    weapon_proficiencies: Mapped[list[ClassWeaponProficiency]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    available_skills: Mapped[list[Skill]] = relationship(
        secondary=class_available_skills,
    )
    spell_slot_progression: Mapped[list[ClassSpellSlotProgression]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ClassSpellSlotProgression.class_level, ClassSpellSlotProgression.spell_level",
    )
    subclasses: Mapped[list[Subclass]] = relationship(
        back_populates="character_class",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Subclass.name, Subclass.id",
    )
    # CLASS-source only: subclass features are exposed through ``Subclass.features``.
    features: Mapped[list[Feature]] = relationship(
        viewonly=True,
        primaryjoin=lambda: and_(
            Feature.class_id == Class.id,
            Feature.source_type == FeatureSourceType.CLASS,
        ),
        order_by="Feature.id",
    )
    starting_items: Mapped[list[SourceItem]] = relationship(
        primaryjoin="Class.id == SourceItem.class_id",
        foreign_keys="SourceItem.class_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    starting_choice_groups: Mapped[list[SourceItemChoiceGroup]] = relationship(
        primaryjoin="Class.id == SourceItemChoiceGroup.class_id",
        foreign_keys="SourceItemChoiceGroup.class_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SourceItemChoiceGroup.sort_order",
    )
    characters: Mapped[list[Character]] = relationship(back_populates="character_class")

    def __repr__(self) -> str:
        return f"<Class(id={self.id}, name='{self.name}')>"
