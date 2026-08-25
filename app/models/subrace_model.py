"""ORM model for the reference table of race subraces (lineages)."""

from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.settings import settings


class Subrace(settings.Base):  # type: ignore
    """
    Reference table of race subraces (e.g. Elf -> High Elf / Wood Elf / Drow).

    Each subrace belongs to exactly one race and may grant its own ability
    bonuses and features (``source_type=SUBRACE``).
    """

    __tablename__ = "subraces"

    id = Column(Integer, primary_key=True)

    race_id = Column(Integer, ForeignKey("races.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=False, default="")

    __table_args__ = (UniqueConstraint("race_id", "name", name="uq_subrace_race_id_name"),)

    race = relationship("Race", back_populates="subraces")
    ability_bonuses = relationship(
        "SubraceAbilityBonus",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    features = relationship(
        "Feature",
        back_populates="subrace",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Feature.id",
    )

    def __repr__(self):
        return f"<Subrace(id={self.id}, name='{self.name}', race_id={self.race_id})>"
