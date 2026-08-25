"""ORM model for the reference table of character backgrounds."""

from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.background_association_models import background_skills
from app.settings import settings


class Background(settings.Base):  # type: ignore
    """
    Reference table of character backgrounds (e.g. Acolyte, Criminal),
    shared across all characters. GM-managed, like Race, Class and Spell.
    """

    __tablename__ = "backgrounds"

    id = Column(Integer, primary_key=True)

    name = Column(String(100), nullable=False, unique=True, index=True)
    personality_traits_suggestions = Column(Text, nullable=False, default="")
    ideals_suggestions = Column(Text, nullable=False, default="")
    bonds_suggestions = Column(Text, nullable=False, default="")
    flaws_suggestions = Column(Text, nullable=False, default="")

    description = Column(Text, nullable=False, default="")

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
    characters = relationship("Character", back_populates="background")

    def __repr__(self):
        return f"<Background(id={self.id}, name='{self.name}')>"
