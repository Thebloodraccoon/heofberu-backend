"""ORM models/tables for race sub-resources: granted skills and ability bonuses."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Integer, Table
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import AbilityScore
from app.models.enums import AbilityScoreType
from app.settings.base import Base

race_skills = Table(
    "race_skills",
    Base.metadata,
    Column("race_id", Integer, ForeignKey("races.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", Integer, ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True),
    # The composite PK is (race_id, skill_id) — a lone `WHERE skill_id = ...`
    # (e.g. the skill-deletion in-use guard) can't use it, hence this index.
    Index("ix_race_skills_skill_id", "skill_id"),
)

race_tags = Table(
    "race_tags",
    Base.metadata,
    Column("race_id", Integer, ForeignKey("races.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="RESTRICT"), primary_key=True),
    # The composite PK is (race_id, tag_id) — a lone `WHERE tag_id = ...`
    # can't use it, hence this index.
    Index("ix_race_tags_tag_id", "tag_id"),
)


class RaceAbilityBonus(Base):
    """Ability score bonus granted by a race, e.g. {race: Elf, ability: DEX, bonus: 2}."""

    __tablename__ = "race_ability_bonuses"
    __table_args__ = (CheckConstraint("bonus BETWEEN -10 AND 10", name="ck_race_ability_bonus_range"),)

    race_id: Mapped[int] = mapped_column(ForeignKey("races.id", ondelete="CASCADE"), primary_key=True)
    ability: Mapped[AbilityScore] = mapped_column(AbilityScoreType, primary_key=True)
    bonus: Mapped[int] = mapped_column(default=0)

    def __repr__(self) -> str:
        return f"<RaceAbilityBonus(race_id={self.race_id}, ability='{self.ability}', bonus={self.bonus})>"
