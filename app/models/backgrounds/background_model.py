"""ORM model for the reference table of character backgrounds."""

from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.backgrounds.background_association_models import background_skills, background_tags
from app.settings import settings


class Background(settings.Base):  # type: ignore
    """
    Reference table of character backgrounds (e.g. Acolyte, Criminal),
    shared across all characters. GM-managed, like Race, Class and Spell.
    """

    __tablename__ = "backgrounds"

    id = Column(Integer, primary_key=True)

    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=False, default="")
    starting_gold = Column(Integer, nullable=False, default=0)

    suggestions = relationship(
        "BackgroundSuggestion",
        back_populates="background",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BackgroundSuggestion.suggestion_type, BackgroundSuggestion.id",
    )
    features = relationship(
        "Feature",
        back_populates="background",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Feature.id",
    )
    granted_skills = relationship(
        "Skill",
        secondary=background_skills,
    )
    starting_items = relationship(
        "SourceItem",
        primaryjoin="Background.id == SourceItem.background_id",
        foreign_keys="SourceItem.background_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    starting_choice_groups = relationship(
        "SourceItemChoiceGroup",
        primaryjoin="Background.id == SourceItemChoiceGroup.background_id",
        foreign_keys="SourceItemChoiceGroup.background_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SourceItemChoiceGroup.sort_order",
    )
    characters = relationship("Character", back_populates="background", passive_deletes=True)
    tags = relationship(
        "Tag",
        secondary=background_tags,
        back_populates="backgrounds",
        order_by="Tag.name",
    )

    def __repr__(self):
        return f"<Background(id={self.id}, name='{self.name}')>"
