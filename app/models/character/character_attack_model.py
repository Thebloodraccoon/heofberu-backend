"""ORM model for character attacks (weapon entries)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import AbilityScore, AttackType, DamageType, DiceType
from app.models.enums import AbilityScoreType, AttackTypeType, DamageTypeType, DiceTypeColumn
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.character.character_model import Character


class Attack(Base):
    """A single attack/weapon entry belonging to a character."""

    __tablename__ = "attacks"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)

    name: Mapped[str] = mapped_column(String(200))
    attack_type: Mapped[AttackType] = mapped_column(AttackTypeType)
    ability: Mapped[AbilityScore] = mapped_column(AbilityScoreType)
    is_proficient: Mapped[bool] = mapped_column(default=True)

    bonus_attack: Mapped[int] = mapped_column(default=0)
    bonus_damage: Mapped[int] = mapped_column(default=0)
    damage_dice_count: Mapped[int | None] = mapped_column()
    damage_dice_type: Mapped[DiceType | None] = mapped_column(DiceTypeColumn)
    damage_type: Mapped[DamageType | None] = mapped_column(DamageTypeType)
    range: Mapped[str] = mapped_column(String(50), default="")
    notes: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        CheckConstraint(
            "damage_dice_count IS NULL OR damage_dice_count BETWEEN 1 AND 100", name="ck_attacks_damage_dice_count"
        ),
    )

    character: Mapped[Character] = relationship(back_populates="attacks")

    def __repr__(self) -> str:
        return f"<Attack(id={self.id}, name='{self.name}', character_id={self.character_id})>"
