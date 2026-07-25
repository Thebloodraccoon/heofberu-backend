from sqlalchemy import Column, ForeignKey, Integer, Table

from app.settings import settings

character_spells = Table(
    "character_spells",
    settings.Base.metadata,
    Column("character_id", Integer, ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
    Column("spell_id", Integer, ForeignKey("spells.id", ondelete="CASCADE"), primary_key=True),
)
