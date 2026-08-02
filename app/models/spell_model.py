from sqlalchemy import ARRAY, Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

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
from app.models.spell_association_models import spell_classes, spell_races
from app.settings import settings


class Spell(settings.Base):  # type: ignore
    """Reference table of spells, shared across all characters."""

    __tablename__ = "spells"

    id = Column(Integer, primary_key=True)

    name = Column(String(300), nullable=False, unique=True, index=True)
    school = Column(SpellSchoolType, nullable=False)
    level = Column(SpellLevelType, nullable=False, index=True)

    cast_time = Column(SpellCastTimeType, nullable=False)
    range_type = Column(SpellRangeTypeType, nullable=False)
    range_value = Column(Integer)

    components = Column(ARRAY(ComponentType), nullable=False, default=list)
    is_material_consumed = Column(Boolean, nullable=False, default=False)
    material = Column(Text)  # material component description, relevant when Component.MATERIAL is in `components`

    is_ritual = Column(Boolean, nullable=False, default=False)

    duration = Column(SpellDurationType, nullable=False)
    is_concentration = Column(Boolean, nullable=False, default=False)

    attack_type = Column(AttackTypeType, nullable=True)  # NULL if the spell has no attack roll
    save_stat = Column(AbilityScoreType, nullable=True)
    damage_type = Column(DamageTypeType, nullable=True)
    damage_dice_count = Column(Integer, nullable=True)  # e.g. 2
    damage_dice_type = Column(DiceTypeColumn, nullable=True)  # e.g. D6 -> "2d6" combined

    # Healing (NULL healing_target means the spell doesn't heal)
    healing_target = Column(HealingTargetType, nullable=True)
    healing_dice_count = Column(Integer, nullable=True)
    healing_dice_type = Column(DiceTypeColumn, nullable=True)

    description = Column(Text, nullable=False)
    higher_levels = Column(Text)

    is_homebrew = Column(Boolean, nullable=False, default=False)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    created_by = relationship("User")

    available_classes = relationship("Class", secondary=spell_classes)
    available_races = relationship("Race", secondary=spell_races)

    def __repr__(self):
        return f"<Spell(id={self.id}, name='{self.name}', level='{self.level}')>"
