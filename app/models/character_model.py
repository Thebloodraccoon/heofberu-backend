"""ORM model for the D&D 5e character sheet."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.models.enums import AbilityScoreType
from app.settings import settings
from app.settings._common import utcnow


class Character(settings.Base):  # type: ignore
    """D&D 5e character sheet. Owned by a single user."""

    __tablename__ = "characters"

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Basic info
    name = Column(String(200), nullable=False, index=True)
    image_path = Column(String(500))
    level = Column(Integer, nullable=False, default=1)

    class_id = Column(Integer, ForeignKey("classes.id", ondelete="RESTRICT"), nullable=False, index=True)
    subclass_id = Column(Integer, ForeignKey("subclasses.id", ondelete="SET NULL"), nullable=True, index=True)
    race_id = Column(Integer, ForeignKey("races.id", ondelete="SET NULL"), index=True)
    subrace_id = Column(Integer, ForeignKey("subraces.id", ondelete="SET NULL"), nullable=True, index=True)
    background_id = Column(Integer, ForeignKey("backgrounds.id", ondelete="SET NULL"), index=True)

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
    has_jack_of_all_trades = Column(Boolean, nullable=False, default=False)

    # Ability scores
    strength = Column(Integer, nullable=False, default=10)
    dexterity = Column(Integer, nullable=False, default=10)
    constitution = Column(Integer, nullable=False, default=10)
    intelligence = Column(Integer, nullable=False, default=10)
    wisdom = Column(Integer, nullable=False, default=10)
    charisma = Column(Integer, nullable=False, default=10)

    # Free-text catch-all for proficiencies not otherwise modeled (tools,
    # languages, armor/weapon proficiencies) — skills and saving throws are
    # modeled as relationships below.
    proficiencies = Column(Text, nullable=False, default="")

    # Free text sections
    traits = Column(Text, nullable=False, default="")
    backstory = Column(Text, nullable=False, default="")
    notes = Column(Text, nullable=False, default="")

    # Currency
    money_gold = Column(Integer, nullable=False, default=0)
    money_silver = Column(Integer, nullable=False, default=0)
    money_copper = Column(Integer, nullable=False, default=0)

    # Spellcasting settings
    spell_ability = Column(AbilityScoreType, nullable=True)
    spell_dc_misc_bonus = Column(Integer, nullable=False, default=0)
    spell_attack_misc_bonus = Column(Integer, nullable=False, default=0)

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

    skill_proficiencies = relationship(
        "CharacterSkillProficiency",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    saving_throw_proficiencies = relationship(
        "CharacterSavingThrowProficiency",
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
    spells = relationship("Spell", secondary="character_spells", viewonly=True)

    character_features = relationship(
        "CharacterFeature",
        back_populates="character",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    features = relationship("Feature", secondary="character_features", viewonly=True)

    character_items = relationship(
        "CharacterItem",
        back_populates="character",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    items = relationship("Item", secondary="character_items", viewonly=True)

    character_feats = relationship(
        "CharacterFeat",
        back_populates="character",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    feats = relationship("Feat", secondary="character_feats", viewonly=True)

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

    __table_args__ = (
        CheckConstraint("level >= 1 AND level <= 20", name="check_character_level_range"),
        CheckConstraint("current_hp >= 0", name="check_current_hp_nonnegative"),
        CheckConstraint("max_hp >= 0", name="check_max_hp_nonnegative"),
        CheckConstraint("temp_hp >= 0", name="check_temp_hp_nonnegative"),
    )

    def __repr__(self):
        return f"<Character(id={self.id}, name='{self.name}', owner_id={self.owner_id})>"
