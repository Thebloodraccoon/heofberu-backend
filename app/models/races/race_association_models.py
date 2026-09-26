"""ORM models/tables for race sub-resources: granted skills and ability bonuses."""

from sqlalchemy import Column, ForeignKey, Index, Integer, Table

from app.models.enums import AbilityScoreType
from app.settings import settings

# races <-> skills (which skills a race grants proficiency in)
race_skills = Table(
    "race_skills",
    settings.Base.metadata,
    Column("race_id", Integer, ForeignKey("races.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", Integer, ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True),
    # The composite PK is (race_id, skill_id) — a lone `WHERE skill_id = ...`
    # (e.g. the skill-deletion in-use guard) can't use it, hence this index.
    Index("ix_race_skills_skill_id", "skill_id"),
)

# races <-> tags (shared Tag dictionary)
race_tags = Table(
    "race_tags",
    settings.Base.metadata,
    Column("race_id", Integer, ForeignKey("races.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="RESTRICT"), primary_key=True),
    # The composite PK is (race_id, tag_id) — a lone `WHERE tag_id = ...`
    # can't use it, hence this index.
    Index("ix_race_tags_tag_id", "tag_id"),
)


class RaceAbilityBonus(settings.Base):  # type: ignore
    """Ability score bonus granted by a race, e.g. {race: Elf, ability: DEX, bonus: 2}."""

    __tablename__ = "race_ability_bonuses"

    race_id = Column(Integer, ForeignKey("races.id", ondelete="CASCADE"), primary_key=True)
    ability = Column(AbilityScoreType, primary_key=True)
    bonus = Column(Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<RaceAbilityBonus(race_id={self.race_id}, ability='{self.ability}', bonus={self.bonus})>"
