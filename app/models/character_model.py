from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.settings import settings


class Character(settings.Base):  # type: ignore
    """D&D 5e character sheet. Owned by a single user."""

    __tablename__ = "characters"

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Basic info
    name = Column(String(200), nullable=False, index=True)
    image_path = Column(String(500))
    level = Column(Integer, nullable=False, default=1)

    character_class = Column(String(100), nullable=False, default="")
    subclass = Column(String(100), nullable=False, default="")
    race_id = Column(Integer, ForeignKey("races.id", ondelete="SET NULL"), index=True)

    # Combat stats
    current_hp = Column(Integer, nullable=False, default=0)
    max_hp = Column(Integer, nullable=False, default=0)
    temp_hp = Column(Integer, nullable=False, default=0)
    hit_dice = Column(String(20), nullable=False, default="")
    speed = Column(Integer, nullable=False, default=30)
    armor_class = Column(Integer, nullable=False, default=10)
    shield = Column(Integer, nullable=False, default=0)
    initiative_bonus = Column(Integer, nullable=False, default=0)
    passive_perception_bonus = Column(Integer, nullable=False, default=0)
    has_jack_of_all_trades = Column(Integer, nullable=False, default=0)

    # Ability scores
    strength = Column(Integer, nullable=False, default=10)
    dexterity = Column(Integer, nullable=False, default=10)
    constitution = Column(Integer, nullable=False, default=10)
    intelligence = Column(Integer, nullable=False, default=10)
    wisdom = Column(Integer, nullable=False, default=10)
    charisma = Column(Integer, nullable=False, default=10)

    # Proficiencies / skills — stored as JSONB (was JSON-in-TEXT in sqlite source)
    skill_proficiencies = Column(JSONB, nullable=False, default=dict)
    saving_throw_proficiencies = Column(String(100), nullable=False, default="")
    proficiencies = Column(Text, nullable=False, default="")

    # Free text sections
    traits = Column(Text, nullable=False, default="")
    feats = Column(Text, nullable=False, default="")
    inventory = Column(Text, nullable=False, default="")
    backstory = Column(Text, nullable=False, default="")
    notes = Column(Text, nullable=False, default="")

    # Currency
    money_gold = Column(Integer, nullable=False, default=0)
    money_silver = Column(Integer, nullable=False, default=0)
    money_copper = Column(Integer, nullable=False, default=0)

    # Spellcasting settings
    spell_ability = Column(String(10))
    spell_dc_misc_bonus = Column(Integer, nullable=False, default=0)
    spell_attack_misc_bonus = Column(Integer, nullable=False, default=0)
    spell_slots = Column(JSONB, nullable=False, default=dict)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    owner = relationship("User", back_populates="characters")
    race = relationship("Race", back_populates="characters")
    attacks = relationship("Attack", back_populates="character", cascade="all, delete-orphan", passive_deletes=True)
    spells = relationship("Spell", secondary="character_spells", back_populates="characters")

    __table_args__ = (
        CheckConstraint("level >= 1 AND level <= 20", name="check_character_level_range"),
        CheckConstraint("current_hp >= 0", name="check_current_hp_nonnegative"),
        CheckConstraint("max_hp >= 0", name="check_max_hp_nonnegative"),
    )

    def __repr__(self):
        return f"<Character(id={self.id}, name='{self.name}', owner_id={self.owner_id})>"
