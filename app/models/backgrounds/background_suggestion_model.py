"""ORM model for a background's suggested personality-card entries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import BackgroundSuggestionType
from app.models.enums import BackgroundSuggestionTypeType
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.backgrounds.background_model import Background


class BackgroundSuggestion(Base):
    """
    One suggested personality-card entry for a background (e.g. Acolyte's
    "I idolize a particular hero of my faith." as a PERSONALITY_TRAIT row).

    Replaces the old ``personality_traits_suggestions``/``ideals_suggestions``/
    ``bonds_suggestions``/``flaws_suggestions`` free-text blobs on
    ``Background`` (one newline-delimited string per field) with one row per
    suggestion, tagged by ``suggestion_type``. Unordered by design — the
    player picks from the set or rolls one at random, not off a numbered list.
    """

    __tablename__ = "background_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    background_id: Mapped[int] = mapped_column(ForeignKey("backgrounds.id", ondelete="CASCADE"), index=True)
    suggestion_type: Mapped[BackgroundSuggestionType] = mapped_column(BackgroundSuggestionTypeType)
    text: Mapped[str] = mapped_column(Text)

    background: Mapped[Background] = relationship(back_populates="suggestions")

    def __repr__(self) -> str:
        return f"<BackgroundSuggestion(background_id={self.background_id}, suggestion_type='{self.suggestion_type}')>"
