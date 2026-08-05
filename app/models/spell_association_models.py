"""Association tables linking spells to the classes and races that grant them."""

from sqlalchemy import Column, ForeignKey, Integer, Table

from app.settings import settings

# spells <-> classes (which classes can learn/prepare a given spell).
# Managed from the Spell side (PUT /spells/{spell_id}/classes), so a spell's
# small, fixed class list is edited in one place rather than hunting through
# every class's spell list. An empty set for a spell means "unrestricted" —
# not tied to any particular class.
spell_classes = Table(
    "spell_classes",
    settings.Base.metadata,
    Column("spell_id", Integer, ForeignKey("spells.id", ondelete="CASCADE"), primary_key=True),
    Column("class_id", Integer, ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True),
)

# spells <-> races (which races grant/allow a given spell, e.g. innate
# racial spellcasting). Same "empty = unrestricted" convention as spell_classes.
spell_races = Table(
    "spell_races",
    settings.Base.metadata,
    Column("spell_id", Integer, ForeignKey("spells.id", ondelete="CASCADE"), primary_key=True),
    Column("race_id", Integer, ForeignKey("races.id", ondelete="CASCADE"), primary_key=True),
)
