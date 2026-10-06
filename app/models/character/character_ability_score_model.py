"""ORM model for cached, precomputed effective ability scores."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.settings._common import utcnow
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.character.character_model import Character


class CharacterAbilityScore(Base):
    """
    Cached, precomputed "effective" ability scores for a character: the base
    score (``Character.strength`` etc.) plus every applicable bonus (race,
    subrace, counted ASI-log increases, granted-feature ASI effects).

    A cache, not a source of truth: the base values on ``Character`` stay
    authoritative. Rows are (re)computed and written only by
    ``CharacterStatsService.refresh`` / ``refresh_many`` — on character
    creation, level-up, ASI/feat/feature grants and GM edits that change a
    source. Read paths (``GET /characters``, ``GET /characters/{id}``) serve
    the row as it is and never recompute; ``GET /characters/{id}/stats``
    always computes fresh. One row per character (``character_id`` is PK and
    FK), so a missing row simply means "never computed yet".
    """

    __tablename__ = "character_ability_scores"

    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)

    strength_total: Mapped[int] = mapped_column(default=10)
    dexterity_total: Mapped[int] = mapped_column(default=10)
    constitution_total: Mapped[int] = mapped_column(default=10)
    intelligence_total: Mapped[int] = mapped_column(default=10)
    wisdom_total: Mapped[int] = mapped_column(default=10)
    charisma_total: Mapped[int] = mapped_column(default=10)

    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    character: Mapped[Character] = relationship(back_populates="ability_score_cache")

    def __repr__(self) -> str:
        return f"<CharacterAbilityScore(character_id={self.character_id})>"
