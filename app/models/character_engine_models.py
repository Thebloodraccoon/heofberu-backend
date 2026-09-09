"""
ORM models for the character side of the Feature/Feat engine (Phase 2).

All "anything a character gets" rows live on the character and remember their
source: a nullable ``source_character_feature_id`` pointing at the granting
``character_features`` row. ``NULL`` = a raw GM / free-form row with no grant
(kept untouched by rebuilds). Effect rows materialized from a grant are
deleted automatically when the grant is deleted via ``ON DELETE CASCADE`` on
``source_character_feature_id`` — the sync service never has to clean up
manually.

Table inventory:
- ``character_feature_choices`` — one row per (grant, choice group, option)
  chosen when a grant was materialized; validates pick_count.
- ``character_skill_proficiencies`` — existing table, gained a nullable
  ``source_character_feature_id`` (see ``character_association_models.py``).
- ``character_saving_throw_proficiencies`` — new; replaces class-only Saves.
- ``character_armor_proficiencies`` — new.
- ``character_weapon_proficiencies`` — new (category OR concrete item).
- ``character_granted_spells`` — new; spells added by features/feats, kept
  separate from the limited ``character_spells`` "known spells" table.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.models.enums import AbilityScoreType, ArmorProficiencyType, WeaponProficiencyType
from app.settings import settings


class CharacterFeatureChoice(settings.Base):  # type: ignore
    """
    One selected option inside a grant's choice group.

    The unique ``(character_feature_id, choice_group_id, choice_option_id)``
    triple prevents double-picking the same option; whether the group is
    fully resolved (the chosen option count == ``pick_count``) is validated
    by the grant materializer service.
    """

    __tablename__ = "character_feature_choices"

    id = Column(Integer, primary_key=True)
    character_feature_id = Column(
        Integer,
        ForeignKey("character_features.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    choice_group_id = Column(
        Integer,
        ForeignKey("feature_choice_groups.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    choice_option_id = Column(
        Integer,
        ForeignKey("feature_choice_options.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "character_feature_id",
            "choice_group_id",
            "choice_option_id",
            name="uq_character_feature_choice_option",
        ),
    )

    character_feature = relationship("CharacterFeature", back_populates="choices")
    choice_group = relationship("FeatureChoiceGroup")
    choice_option = relationship("FeatureChoiceOption")

    def __repr__(self):
        return (
            f"<CharacterFeatureChoice(character_feature_id={self.character_feature_id}, "
            f"group_id={self.choice_group_id}, option_id={self.choice_option_id})>"
        )


class CharacterSavingThrowProficiency(settings.Base):  # type: ignore
    """A character's saving-throw proficiency (materialized from a grant or GM-set)."""

    __tablename__ = "character_saving_throw_proficiencies"

    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    ability = Column(AbilityScoreType, nullable=False)
    source_character_feature_id = Column(
        Integer,
        ForeignKey("character_features.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    __table_args__ = (UniqueConstraint("character_id", "ability", name="uq_character_saving_throw_ability"),)

    character = relationship("Character", back_populates="saving_throw_proficiencies")
    source_grant = relationship("CharacterFeature")

    def __repr__(self):
        return (
            f"<CharacterSavingThrowProficiency(character_id={self.character_id}, "
            f"ability='{self.ability}', source={self.source_character_feature_id})>"
        )


class CharacterArmorProficiency(settings.Base):  # type: ignore
    """A character's armor proficiency (LIGHT/MEDIUM/HEAVY/SHIELD)."""

    __tablename__ = "character_armor_proficiencies"

    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    armor_type = Column(ArmorProficiencyType, nullable=False)
    source_character_feature_id = Column(
        Integer,
        ForeignKey("character_features.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    __table_args__ = (UniqueConstraint("character_id", "armor_type", name="uq_character_armor_proficiency_type"),)

    character = relationship("Character", back_populates="armor_proficiencies")
    source_grant = relationship("CharacterFeature")

    def __repr__(self):
        return (
            f"<CharacterArmorProficiency(character_id={self.character_id}, "
            f"armor_type='{self.armor_type}', source={self.source_character_feature_id})>"
        )


class CharacterWeaponProficiency(settings.Base):  # type: ignore
    """
    A character's weapon proficiency: a whole category (SIMPLE/MARTIAL) or a
    single concrete item — exactly one of the two, mirroring
    ``FeatureWeaponProficiencyEffect``.
    """

    __tablename__ = "character_weapon_proficiencies"

    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    weapon_category = Column(WeaponProficiencyType, nullable=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=True, index=True)
    source_character_feature_id = Column(
        Integer,
        ForeignKey("character_features.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    __table_args__ = (
        UniqueConstraint("character_id", "item_id", name="uq_character_weapon_proficiency_item"),
        CheckConstraint(
            "(weapon_category IS NOT NULL AND item_id IS NULL) OR (weapon_category IS NULL AND item_id IS NOT NULL)",
            name="ck_character_weapon_proficiency_one_target",
        ),
    )

    character = relationship("Character", back_populates="weapon_proficiencies")
    item = relationship("Item")
    source_grant = relationship("CharacterFeature")

    def __repr__(self):
        return (
            f"<CharacterWeaponProficiency(character_id={self.character_id}, "
            f"weapon_category='{self.weapon_category}', item_id={self.item_id}, "
            f"source={self.source_character_feature_id})>"
        )


class CharacterGrantedSpell(settings.Base):  # type: ignore
    """
    A spell granted to a character by a feature/feat — deliberately separate
    from the limited "known spells" table ``character_spells``.

    Known spells are capped by ``CharacterSpellSlot.total``; granted spells
    never compete for that budget unless ``counts_against_known_limit`` is
    True (content explicitly sold as "learn one additional spell as part of
    your known list"). ``always_prepared`` (default True) means the spell is
    always available without slotting. A character may hold the same spell
    from multiple grants; the unique constraint therefore keys on
    ``source_character_feature_id`` rather than the plain pair.
    """

    __tablename__ = "character_granted_spells"

    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    spell_id = Column(Integer, ForeignKey("spells.id", ondelete="RESTRICT"), nullable=False, index=True)
    always_prepared = Column(Boolean, nullable=False, default=True)
    counts_against_known_limit = Column(Boolean, nullable=False, default=False)
    source_character_feature_id = Column(
        Integer,
        ForeignKey("character_features.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    character = relationship("Character", back_populates="granted_spells")
    spell = relationship("Spell")
    source_grant = relationship("CharacterFeature")

    def __repr__(self):
        return (
            f"<CharacterGrantedSpell(character_id={self.character_id}, spell_id={self.spell_id}, "
            f"source={self.source_character_feature_id})>"
        )
