"""ORM model for the GM proficiency audit log."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import relationship

from app.models.enums import (
    AbilityScoreType,
    ArmorProficiencyType,
    ProficiencyAuditActionType,
    ProficiencyTypeType,
    WeaponProficiencyType,
)
from app.settings import settings


class CharacterProficiencyAuditLog(settings.Base):  # type: ignore
    """
    One GM change to a character's skill/saving-throw/armor/weapon
    proficiency rows (add, remove, or an expertise toggle).

    The materialized proficiency tables themselves carry no history — a
    row disappearing when a GM removes it is otherwise silent. This table
    is an append-only log, never updated or read back into gameplay logic,
    purely for "who changed what and when" visibility. Exactly one of
    ``skill_id`` / ``ability`` / ``armor_type`` / (``weapon_category`` or
    ``item_id``) is set, matching ``proficiency_type``.
    """

    __tablename__ = "character_proficiency_audit_log"

    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    proficiency_type = Column(ProficiencyTypeType, nullable=False)
    action = Column(ProficiencyAuditActionType, nullable=False)

    skill_id = Column(Integer, ForeignKey("skills.id", ondelete="SET NULL"), nullable=True)
    ability = Column(AbilityScoreType, nullable=True)
    armor_type = Column(ArmorProficiencyType, nullable=True)
    weapon_category = Column(WeaponProficiencyType, nullable=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="SET NULL"), nullable=True)

    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    notes = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    character = relationship("Character")
    skill = relationship("Skill")
    item = relationship("Item")
    actor = relationship("User")

    def __repr__(self):
        return (
            f"<CharacterProficiencyAuditLog(character_id={self.character_id}, "
            f"proficiency_type='{self.proficiency_type}', action='{self.action}')>"
        )
