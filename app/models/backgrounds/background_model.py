"""ORM model for the reference table of character backgrounds."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.backgrounds.background_association_models import background_skills, background_tags
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.backgrounds.background_suggestion_model import BackgroundSuggestion
    from app.models.character.character_model import Character
    from app.models.features.feature_model import Feature
    from app.models.items.item_source_choice_model import SourceItemChoiceGroup
    from app.models.items.item_source_model import SourceItem
    from app.models.skill_model import Skill
    from app.models.tag_model import Tag


class Background(Base):
    """
    Reference table of character backgrounds (e.g. Acolyte, Criminal),
    shared across all characters. GM-managed, like Race, Class and Spell.
    """

    __tablename__ = "backgrounds"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    starting_gold: Mapped[int] = mapped_column(default=0)

    suggestions: Mapped[list[BackgroundSuggestion]] = relationship(
        back_populates="background",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BackgroundSuggestion.suggestion_type, BackgroundSuggestion.id",
    )
    features: Mapped[list[Feature]] = relationship(
        back_populates="background",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Feature.id",
    )
    granted_skills: Mapped[list[Skill]] = relationship(
        secondary=background_skills,
    )
    starting_items: Mapped[list[SourceItem]] = relationship(
        primaryjoin="Background.id == SourceItem.background_id",
        foreign_keys="SourceItem.background_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    starting_choice_groups: Mapped[list[SourceItemChoiceGroup]] = relationship(
        primaryjoin="Background.id == SourceItemChoiceGroup.background_id",
        foreign_keys="SourceItemChoiceGroup.background_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SourceItemChoiceGroup.sort_order",
    )
    characters: Mapped[list[Character]] = relationship(back_populates="background", passive_deletes=True)
    tags: Mapped[list[Tag]] = relationship(
        secondary=background_tags,
        back_populates="backgrounds",
        order_by="Tag.name",
    )

    def __repr__(self) -> str:
        return f"<Background(id={self.id}, name='{self.name}')>"
