from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.enums import AbilityScoreType, AttackTypeType, DamageTypeType
from app.settings import settings


class Attack(settings.Base):  # type: ignore
    """A single attack/weapon entry belonging to a character."""

    __tablename__ = "attacks"

    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(200), nullable=False)
    attack_type = Column(AttackTypeType, nullable=False)
    ability = Column(AbilityScoreType, nullable=False)
    is_proficient = Column(Boolean, nullable=False, default=True)

    bonus_attack = Column(Integer, nullable=False, default=0)
    bonus_damage = Column(Integer, nullable=False, default=0)
    damage_dice = Column(String(30), nullable=False, default="")
    damage_type = Column(DamageTypeType, nullable=True)
    range = Column(String(50), nullable=False, default="")
    notes = Column(Text, nullable=False, default="")

    character = relationship("Character", back_populates="attacks")

    def __repr__(self):
        return f"<Attack(id={self.id}, name='{self.name}', character_id={self.character_id})>"
