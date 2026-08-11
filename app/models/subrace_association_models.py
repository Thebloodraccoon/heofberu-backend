"""ORM models/tables for subrace sub-resources: ability bonuses."""

from sqlalchemy import Column, ForeignKey, Integer

from app.models.enums import AbilityScoreType
from app.settings import settings


class SubraceAbilityBonus(settings.Base):  # type: ignore
    """Ability score bonus granted by a subrace, e.g. {subrace: Hill Dwarf, ability: WIS, bonus: 1}."""

    __tablename__ = "subrace_ability_bonuses"

    subrace_id = Column(Integer, ForeignKey("subraces.id", ondelete="CASCADE"), primary_key=True)
    ability = Column(AbilityScoreType, primary_key=True)
    bonus = Column(Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<SubraceAbilityBonus(subrace_id={self.subrace_id}, ability='{self.ability}', bonus={self.bonus})>"
