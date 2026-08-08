"""ORM model for the reference table of character backgrounds."""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
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

    is_homebrew = Column(Boolean, nullable=False, default=False)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # BACKGROUND-source features granted by this background (e.g. the
    # Acolyte's "Shelter of the Faithful"). Created nested in the same
    # request as the background and automatically granted to any character
    # bearing it — see ``sync_progression_features``.
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
    characters = relationship("Character", back_populates="background")
    created_by = relationship("User")

    def __repr__(self):
        return f"<Background(id={self.id}, name='{self.name}')>"
