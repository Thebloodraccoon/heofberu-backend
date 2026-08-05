"""Association table linking backgrounds to the skills they grant proficiency in."""

from sqlalchemy import Column, ForeignKey, Integer, Table

from app.settings import settings

# backgrounds <-> skills (which skills a background grants proficiency in)
background_skills = Table(
    "background_skills",
    settings.Base.metadata,
    Column("background_id", Integer, ForeignKey("backgrounds.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", Integer, ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True),
)
