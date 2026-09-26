"""ORM models/tables for subrace sub-resources: ability bonuses and tags."""

from sqlalchemy import Column, ForeignKey, Index, Integer, Table

from app.models.enums import AbilityScoreType
from app.settings import settings

# subraces <-> tags (shared Tag dictionary, e.g. "Sutrice", "Nordavingar")
subrace_tags = Table(
    "subrace_tags",
    settings.Base.metadata,
    Column("subrace_id", Integer, ForeignKey("subraces.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="RESTRICT"), primary_key=True),
    # The composite PK is (subrace_id, tag_id) — a lone `WHERE tag_id = ...`
    # can't use it, hence this index.
    Index("ix_subrace_tags_tag_id", "tag_id"),
)


class SubraceAbilityBonus(settings.Base):  # type: ignore
    """Ability score bonus granted by a subrace, e.g. {subrace: Hill Dwarf, ability: WIS, bonus: 1}."""

    __tablename__ = "subrace_ability_bonuses"

    subrace_id = Column(Integer, ForeignKey("subraces.id", ondelete="CASCADE"), primary_key=True)
    ability = Column(AbilityScoreType, primary_key=True)
    bonus = Column(Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<SubraceAbilityBonus(subrace_id={self.subrace_id}, ability='{self.ability}', bonus={self.bonus})>"
