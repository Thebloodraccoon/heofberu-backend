"""Association tables linking spells to the classes, subclasses, races, and subraces that grant them."""

from sqlalchemy import Column, ForeignKey, Index, Integer, Table

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
    # The PK leads with spell_id; this serves "spells of X" and the ON DELETE CASCADE from classes.
    Index("ix_spell_classes_class_id", "class_id"),
)

# spells <-> subclasses (which subclasses grant/allow a given spell). Same
# "empty = unrestricted" convention as spell_classes.
spell_subclasses = Table(
    "spell_subclasses",
    settings.Base.metadata,
    Column("spell_id", Integer, ForeignKey("spells.id", ondelete="CASCADE"), primary_key=True),
    Column("subclass_id", Integer, ForeignKey("subclasses.id", ondelete="CASCADE"), primary_key=True),
    # The PK leads with spell_id; this serves "spells of X" and the ON DELETE CASCADE from subclasses.
    Index("ix_spell_subclasses_subclass_id", "subclass_id"),
)

# spells <-> races (which races grant/allow a given spell, e.g. innate
# racial spellcasting). Same "empty = unrestricted" convention as spell_classes.
spell_races = Table(
    "spell_races",
    settings.Base.metadata,
    Column("spell_id", Integer, ForeignKey("spells.id", ondelete="CASCADE"), primary_key=True),
    Column("race_id", Integer, ForeignKey("races.id", ondelete="CASCADE"), primary_key=True),
    # The PK leads with spell_id; this serves "spells of X" and the ON DELETE CASCADE from races.
    Index("ix_spell_races_race_id", "race_id"),
)

# spells <-> subraces (which subraces grant/allow a given spell). Same
# "empty = unrestricted" convention as spell_classes.
spell_subraces = Table(
    "spell_subraces",
    settings.Base.metadata,
    Column("spell_id", Integer, ForeignKey("spells.id", ondelete="CASCADE"), primary_key=True),
    Column("subrace_id", Integer, ForeignKey("subraces.id", ondelete="CASCADE"), primary_key=True),
    # The PK leads with spell_id; this serves "spells of X" and the ON DELETE CASCADE from subraces.
    Index("ix_spell_subraces_subrace_id", "subrace_id"),
)
