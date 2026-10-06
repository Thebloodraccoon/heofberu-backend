"""ORM model for the reference table of playable races."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import RaceSize
from app.models.enums import RaceSizeType
from app.models.races.race_association_models import race_skills, race_tags
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.character.character_model import Character
    from app.models.features.feature_model import Feature
    from app.models.races.race_association_models import RaceAbilityBonus
    from app.models.races.subrace_model import Subrace
    from app.models.skill_model import Skill
    from app.models.tag_model import Tag


class Race(Base):
    """Reference table of playable races, shared across all characters."""

    __tablename__ = "races"
    __table_args__ = (CheckConstraint("speed BETWEEN 0 AND 200", name="ck_races_speed"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    size: Mapped[RaceSize] = mapped_column(RaceSizeType)
    speed: Mapped[int] = mapped_column(default=30)

    description: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str | None] = mapped_column(String(512))

    ability_bonuses: Mapped[list[RaceAbilityBonus]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    granted_skills: Mapped[list[Skill]] = relationship(
        secondary=race_skills,
    )
    characters: Mapped[list[Character]] = relationship(back_populates="race", passive_deletes=True)
    features: Mapped[list[Feature]] = relationship(
        back_populates="race",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Feature.id",
    )
    subraces: Mapped[list[Subrace]] = relationship(
        back_populates="race",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Subrace.name, Subrace.id",
    )
    tags: Mapped[list[Tag]] = relationship(
        secondary=race_tags,
        back_populates="races",
        order_by="Tag.name",
    )

    def __repr__(self) -> str:
        return f"<Race(id={self.id}, name='{self.name}')>"
