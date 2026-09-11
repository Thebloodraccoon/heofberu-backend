"""Association table linking backgrounds to the skills they grant proficiency in."""

from sqlalchemy import Column, ForeignKey, Index, Integer, Table

from app.settings import settings

# backgrounds <-> skills (which skills a background grants proficiency in)
background_skills = Table(
    "background_skills",
    settings.Base.metadata,
    Column("background_id", Integer, ForeignKey("backgrounds.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", Integer, ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True),
    # The composite PK is (background_id, skill_id) — a lone `WHERE skill_id = ...`
    # (e.g. the skill-deletion in-use guard) can't use it, hence this index.
    Index("ix_background_skills_skill_id", "skill_id"),
)
