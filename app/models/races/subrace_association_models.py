"""ORM models/tables for subrace sub-resources: ability bonuses and tags."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Integer, Table
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import AbilityScore
from app.models.enums import AbilityScoreType
from app.settings.base import Base

subrace_tags = Table(
    "subrace_tags",
    Base.metadata,
    Column("subrace_id", Integer, ForeignKey("subraces.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="RESTRICT"), primary_key=True),
    # The composite PK is (subrace_id, tag_id) — a lone `WHERE tag_id = ...`
    # can't use it, hence this index.
    Index("ix_subrace_tags_tag_id", "tag_id"),
)


class SubraceAbilityBonus(Base):
    """Ability score bonus granted by a subrace, e.g. {subrace: Hill Dwarf, ability: WIS, bonus: 1}."""

    __tablename__ = "subrace_ability_bonuses"
    __table_args__ = (CheckConstraint("bonus BETWEEN -10 AND 10", name="ck_subrace_ability_bonus_range"),)

    subrace_id: Mapped[int] = mapped_column(ForeignKey("subraces.id", ondelete="CASCADE"), primary_key=True)
    ability: Mapped[AbilityScore] = mapped_column(AbilityScoreType, primary_key=True)
    bonus: Mapped[int] = mapped_column(default=0)

    def __repr__(self) -> str:
        return f"<SubraceAbilityBonus(subrace_id={self.subrace_id}, ability='{self.ability}', bonus={self.bonus})>"
