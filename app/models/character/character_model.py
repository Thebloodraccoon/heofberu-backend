"""ORM model for the D&D 5e character sheet."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.settings._common import utcnow
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.backgrounds.background_model import Background
    from app.models.character.character_ability_score_model import CharacterAbilityScore
    from app.models.character.character_asi_choice_model import CharacterASIChoice
    from app.models.character.character_attack_model import Attack
    from app.models.character.character_backstory_model import CharacterBackstory
    from app.models.character.character_condition_model import CharacterCondition
    from app.models.character.character_feature_model import CharacterFeature
    from app.models.character.character_item_model import CharacterItem
    from app.models.character.character_proficiency_model import CharacterProficiency
    from app.models.character.character_spell_model import CharacterGrantedSpell, CharacterSpell, CharacterSpellSlot
    from app.models.classes.class_model import Class
    from app.models.classes.subclass_model import Subclass
    from app.models.races.race_model import Race
    from app.models.races.subrace_model import Subrace
    from app.models.user_model import User


class Character(Base):
    """D&D 5e character sheet. Owned by a single user."""

    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    name: Mapped[str] = mapped_column(String(200), index=True)
    level: Mapped[int] = mapped_column(default=1)

    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="RESTRICT"), index=True)
    subclass_id: Mapped[int | None] = mapped_column(ForeignKey("subclasses.id", ondelete="SET NULL"), index=True)
    race_id: Mapped[int | None] = mapped_column(ForeignKey("races.id", ondelete="SET NULL"), index=True)
    subrace_id: Mapped[int | None] = mapped_column(ForeignKey("subraces.id", ondelete="SET NULL"), index=True)
    background_id: Mapped[int | None] = mapped_column(ForeignKey("backgrounds.id", ondelete="SET NULL"), index=True)

    current_hp: Mapped[int] = mapped_column(default=0)
    max_hp: Mapped[int] = mapped_column(default=0)
    temp_hp: Mapped[int] = mapped_column(default=0)

    speed: Mapped[int] = mapped_column(default=30)
    armor_class: Mapped[int] = mapped_column(default=10)
    shield: Mapped[int] = mapped_column(default=0)

    strength: Mapped[int] = mapped_column(default=10)
    dexterity: Mapped[int] = mapped_column(default=10)
    constitution: Mapped[int] = mapped_column(default=10)
    intelligence: Mapped[int] = mapped_column(default=10)
    wisdom: Mapped[int] = mapped_column(default=10)
    charisma: Mapped[int] = mapped_column(default=10)

    notes: Mapped[str] = mapped_column(Text, default="")

    # 0-13 points the GM grants; unlike 5e's boolean it is a stockpile the player spends down.
    inspiration: Mapped[int] = mapped_column(default=0)

    personality_traits: Mapped[str] = mapped_column(Text, default="")
    ideals: Mapped[str] = mapped_column(Text, default="")
    bonds: Mapped[str] = mapped_column(Text, default="")
    flaws: Mapped[str] = mapped_column(Text, default="")

    money_gold: Mapped[int] = mapped_column(default=0)
    money_silver: Mapped[int] = mapped_column(default=0)
    money_copper: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    owner: Mapped[User] = relationship(back_populates="characters")
    character_class: Mapped[Class] = relationship(back_populates="characters")
    subclass: Mapped[Subclass | None] = relationship()
    race: Mapped[Race | None] = relationship(back_populates="characters")
    subrace: Mapped[Subrace | None] = relationship()
    background: Mapped[Background | None] = relationship(back_populates="characters")

    attacks: Mapped[list[Attack]] = relationship(
        back_populates="character", cascade="all, delete-orphan", passive_deletes=True
    )

    proficiencies: Mapped[list[CharacterProficiency]] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    granted_spells: Mapped[list[CharacterGrantedSpell]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    spell_slots: Mapped[list[CharacterSpellSlot]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    character_spells: Mapped[list[CharacterSpell]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    character_features: Mapped[list[CharacterFeature]] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    character_items: Mapped[list[CharacterItem]] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    conditions: Mapped[list[CharacterCondition]] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    asi_choices: Mapped[list[CharacterASIChoice]] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    ability_score_cache: Mapped[CharacterAbilityScore | None] = relationship(
        back_populates="character",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    backstory: Mapped[CharacterBackstory | None] = relationship(
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

    def __repr__(self) -> str:
        return f"<Character(id={self.id}, name='{self.name}', owner_id={self.owner_id})>"
