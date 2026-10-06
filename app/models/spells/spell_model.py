"""ORM model for the reference table of spells."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import (
    AbilityScore,
    AttackType,
    Component,
    DamageType,
    DiceType,
    HealingTarget,
    SpellCastTime,
    SpellDuration,
    SpellLevel,
    SpellRangeType,
    SpellSchool,
)
from app.models.enums import (
    AbilityScoreType,
    AttackTypeType,
    ComponentType,
    DamageTypeType,
    DiceTypeColumn,
    HealingTargetType,
    SpellCastTimeType,
    SpellDurationType,
    SpellLevelType,
    SpellRangeTypeType,
    SpellSchoolType,
)
from app.models.spells.spell_association_models import spell_classes, spell_races, spell_subclasses, spell_subraces
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.classes.class_model import Class
    from app.models.classes.subclass_model import Subclass
    from app.models.races.race_model import Race
    from app.models.races.subrace_model import Subrace


class Spell(Base):
    """Reference table of spells, shared across all characters."""

    __tablename__ = "spells"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    school: Mapped[SpellSchool] = mapped_column(SpellSchoolType)
    level: Mapped[SpellLevel] = mapped_column(SpellLevelType, index=True)

    cast_time: Mapped[SpellCastTime] = mapped_column(SpellCastTimeType)
    range_type: Mapped[SpellRangeType] = mapped_column(SpellRangeTypeType)
    range_value: Mapped[int | None] = mapped_column()

    components: Mapped[list[Component]] = mapped_column(ARRAY(ComponentType), default=list)
    is_material_consumed: Mapped[bool] = mapped_column(default=False)
    # material component description, relevant when Component.MATERIAL is in `components`
    material: Mapped[str | None] = mapped_column(Text)

    is_ritual: Mapped[bool] = mapped_column(default=False)

    duration: Mapped[SpellDuration] = mapped_column(SpellDurationType)
    is_concentration: Mapped[bool] = mapped_column(default=False)

    attack_type: Mapped[AttackType | None] = mapped_column(AttackTypeType)  # NULL if the spell has no attack roll
    save_stat: Mapped[AbilityScore | None] = mapped_column(AbilityScoreType)
    damage_type: Mapped[DamageType | None] = mapped_column(DamageTypeType)
    damage_dice_count: Mapped[int | None] = mapped_column()  # e.g. 2
    damage_dice_type: Mapped[DiceType | None] = mapped_column(DiceTypeColumn)  # e.g. D6 -> "2d6" combined

    # Healing (NULL healing_target means the spell doesn't heal)
    healing_target: Mapped[HealingTarget | None] = mapped_column(HealingTargetType)
    healing_dice_count: Mapped[int | None] = mapped_column()
    healing_dice_type: Mapped[DiceType | None] = mapped_column(DiceTypeColumn)

    description: Mapped[str] = mapped_column(Text)
    higher_levels: Mapped[str | None] = mapped_column(Text)

    available_classes: Mapped[list[Class]] = relationship(secondary=spell_classes, order_by="Class.name")
    available_subclasses: Mapped[list[Subclass]] = relationship(secondary=spell_subclasses, order_by="Subclass.name")
    available_races: Mapped[list[Race]] = relationship(secondary=spell_races, order_by="Race.name")
    available_subraces: Mapped[list[Subrace]] = relationship(secondary=spell_subraces, order_by="Subrace.name")

    def __repr__(self) -> str:
        return f"<Spell(id={self.id}, name='{self.name}', level='{self.level}')>"
