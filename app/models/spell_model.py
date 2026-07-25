from sqlalchemy import Boolean, Column, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from app.settings import settings


class Spell(settings.Base):  # type: ignore
    """Reference table of spells, shared across all characters."""

    __tablename__ = "spells"

    id = Column(Integer, primary_key=True)

    name = Column(String(300), nullable=False, unique=True, index=True)
    school = Column(String(50), nullable=False)
    level = Column(String(20), nullable=False, index=True)  # e.g. CANTRIP, LEVEL_1..LEVEL_9

    cast_time = Column(String(50), nullable=False)
    range_type = Column(String(30), nullable=False)
    range_value = Column(Integer)

    components = Column(String(100), nullable=False)  # e.g. "VERBAL,SOMATIC,MATERIAL"
    material = Column(Text)
    is_ritual = Column(Boolean, nullable=False, default=False)

    duration = Column(String(50), nullable=False)
    is_concentration = Column(Boolean, nullable=False, default=False)

    attack_type = Column(String(20), nullable=False, default="NONE")
    save_stat = Column(String(10))
    damage_type = Column(String(30))
    damage_dice = Column(String(30))

    description = Column(Text, nullable=False)
    higher_levels = Column(Text)

    characters = relationship("Character", secondary="character_spells", back_populates="spells")

    __table_args__ = (Index("idx_spell_level", "level"),)

    def __repr__(self):
        return f"<Spell(id={self.id}, name='{self.name}', level='{self.level}')>"
