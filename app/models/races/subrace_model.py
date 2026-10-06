"""ORM model for the reference table of race subraces (lineages)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.features.feature_model import Feature
    from app.models.races.race_model import Race
    from app.models.races.subrace_association_models import SubraceAbilityBonus
    from app.models.tag_model import Tag


class Subrace(Base):
    """
    Reference table of race subraces (e.g. Elf -> High Elf / Wood Elf / Drow).

    Each subrace belongs to exactly one race and may grant its own ability
    bonuses and features (``source_type=SUBRACE``).
    """

    __tablename__ = "subraces"

    id: Mapped[int] = mapped_column(primary_key=True)

    # No own index: ``uq_subrace_race_id_name`` already leads with ``race_id``.
    race_id: Mapped[int] = mapped_column(ForeignKey("races.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str | None] = mapped_column(String(512))

    __table_args__ = (UniqueConstraint("race_id", "name", name="uq_subrace_race_id_name"),)

    race: Mapped[Race] = relationship(back_populates="subraces")
    ability_bonuses: Mapped[list[SubraceAbilityBonus]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    features: Mapped[list[Feature]] = relationship(
        back_populates="subrace",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Feature.id",
    )
    tags: Mapped[list[Tag]] = relationship(
        secondary="subrace_tags",
        back_populates="subraces",
        order_by="Tag.name",
    )

    def __repr__(self) -> str:
        return f"<Subrace(id={self.id}, name='{self.name}', race_id={self.race_id})>"
