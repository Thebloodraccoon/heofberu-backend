"""ORM model for the D&D 5e character sheet."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.settings import settings
from app.settings._common import utcnow


class Character(settings.Base):  # type: ignore
    """D&D 5e character sheet. Owned by a single user."""

    __tablename__ = "characters"

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(200), nullable=False, index=True)
    level = Column(Integer, nullable=False, default=1)

    class_id = Column(Integer, ForeignKey("classes.id", ondelete="RESTRICT"), nullable=False, index=True)
    subclass_id = Column(Integer, ForeignKey("subclasses.id", ondelete="SET NULL"), nullable=True, index=True)
    race_id = Column(Integer, ForeignKey("races.id", ondelete="SET NULL"), index=True)
    subrace_id = Column(Integer, ForeignKey("subraces.id", ondelete="SET NULL"), nullable=True, index=True)
    background_id = Column(Integer, ForeignKey("backgrounds.id", ondelete="SET NULL"), nullable=True, index=True)

    current_hp = Column(Integer, nullable=False, default=0)
    max_hp = Column(Integer, nullable=False, default=0)
    temp_hp = Column(Integer, nullable=False, default=0)

    speed = Column(Integer, nullable=False, default=30)
    armor_class = Column(Integer, nullable=False, default=10)
    shield = Column(Integer, nullable=False, default=0)

    strength = Column(Integer, nullable=False, default=10)
    dexterity = Column(Integer, nullable=False, default=10)
    constitution = Column(Integer, nullable=False, default=10)
    intelligence = Column(Integer, nullable=False, default=10)
    wisdom = Column(Integer, nullable=False, default=10)
    charisma = Column(Integer, nullable=False, default=10)

    notes = Column(Text, nullable=False, default="")

    # 0-13 points the GM grants; unlike 5e's boolean it is a stockpile the player spends down.
    inspiration = Column(Integer, nullable=False, default=0)

    personality_traits = Column(Text, nullable=False, default="")
    ideals = Column(Text, nullable=False, default="")
    bonds = Column(Text, nullable=False, default="")
    flaws = Column(Text, nullable=False, default="")

    money_gold = Column(Integer, nullable=False, default=0)
    money_silver = Column(Integer, nullable=False, default=0)
    money_copper = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
    )

    owner = relationship("User", back_populates="characters")
    character_class = relationship("Class", back_populates="characters")
    subclass = relationship("Subclass")
    race = relationship("Race", back_populates="characters")
    subrace = relationship("Subrace")
    background = relationship("Background", back_populates="characters")

    attacks = relationship("Attack", back_populates="character", cascade="all, delete-orphan", passive_deletes=True)

    proficiencies = relationship(
        "CharacterProficiency",
        back_populates="character",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    granted_spells = relationship(
        "CharacterGrantedSpell",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    spell_slots = relationship(
        "CharacterSpellSlot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    character_spells = relationship(
        "CharacterSpell",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    character_features = relationship(
        "CharacterFeature",
        back_populates="character",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    character_items = relationship(
        "CharacterItem",
        back_populates="character",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    conditions = relationship(
        "CharacterCondition",
        back_populates="character",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    asi_choices = relationship(
        "CharacterASIChoice",
        back_populates="character",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    ability_score_cache = relationship(
        "CharacterAbilityScore",
        back_populates="character",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    backstory = relationship(
        "CharacterBackstory",
        back_populates="character",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("level >= 1 AND level <= 20", name="check_character_level_range"),
        CheckConstraint("current_hp >= 0", name="check_current_hp_nonnegative"),
        CheckConstraint("max_hp >= 0", name="check_max_hp_nonnegative"),
        CheckConstraint("temp_hp >= 0", name="check_temp_hp_nonnegative"),
        CheckConstraint("inspiration >= 0 AND inspiration <= 13", name="check_inspiration_range"),
        CheckConstraint("current_hp <= max_hp", name="ck_characters_current_hp_le_max_hp"),
        CheckConstraint("armor_class >= 0 AND shield >= 0 AND speed >= 0", name="ck_characters_combat_stats"),
        CheckConstraint("money_gold >= 0 AND money_silver >= 0 AND money_copper >= 0", name="ck_characters_money"),
        # ``GET /characters`` filters by owner and sorts by (name, id); replaces the bare owner_id index.
        Index("ix_characters_owner_id_name", "owner_id", "name", "id"),
        # ``ILIKE '%x%'`` name search (pg_trgm is installed by migration 0001).
        Index("ix_characters_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}),
    )

    def __repr__(self):
        return f"<Character(id={self.id}, name='{self.name}', owner_id={self.owner_id})>"
