from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.enums import (
    AbilityScoreType,
    AttackTypeType,
    DamageTypeType,
    SpellLevelType,
    SpellRangeTypeType,
    SpellSchoolType,
)
from app.settings import settings


class Spell(settings.Base):  # type: ignore
    """Reference table of spells, shared across all characters."""

    __tablename__ = "spells"

    id = Column(Integer, primary_key=True)

    name = Column(String(300), nullable=False, unique=True, index=True)
    school = Column(SpellSchoolType, nullable=False)
    level = Column(SpellLevelType, nullable=False, index=True)

    cast_time = Column(String(50), nullable=False)
    range_type = Column(SpellRangeTypeType, nullable=False)
    range_value = Column(Integer)

    components = Column(String(100), nullable=False)  # e.g. "VERBAL,SOMATIC,MATERIAL"
    material = Column(Text)
    is_ritual = Column(Boolean, nullable=False, default=False)

    duration = Column(String(50), nullable=False)
    is_concentration = Column(Boolean, nullable=False, default=False)

    attack_type = Column(AttackTypeType, nullable=True)  # NULL if the spell has no attack roll
    save_stat = Column(AbilityScoreType, nullable=True)
    damage_type = Column(DamageTypeType, nullable=True)
    damage_dice = Column(String(30), nullable=True)

    description = Column(Text, nullable=False)
    higher_levels = Column(Text)

    is_homebrew = Column(Boolean, nullable=False, default=False)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    created_by = relationship("User")

    def __repr__(self):
        return f"<Spell(id={self.id}, name='{self.name}', level='{self.level}')>"
