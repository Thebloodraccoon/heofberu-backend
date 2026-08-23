"""ORM model for the reference table of discrete rules features."""

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.enums import FeatureSourceTypeType
from app.settings import settings


class Feature(settings.Base):  # type: ignore
    """
    Reference table of discrete rules features: class/subclass features
    (e.g. 'Rage', 'Sneak Attack', 'Extra Attack'), racial and subrace traits,
    and background features. ``source_type`` + the relevant FK
    indicate where the feature comes from; ``level`` is only meaningful for
    CLASS / SUBCLASS features. Feats grant no features (a feat is de facto
    its own feature).
    """

    __tablename__ = "features"

    id = Column(Integer, primary_key=True)

    name = Column(String(200), nullable=False, index=True)
    source_type = Column(FeatureSourceTypeType, nullable=False)

    # Populated depending on source_type; nullable since only one applies per row.
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=True, index=True)
    subclass_id = Column(Integer, ForeignKey("subclasses.id", ondelete="CASCADE"), nullable=True, index=True)

    race_id = Column(Integer, ForeignKey("races.id", ondelete="CASCADE"), nullable=True, index=True)
    subrace_id = Column(Integer, ForeignKey("subraces.id", ondelete="CASCADE"), nullable=True, index=True)

    background_id = Column(Integer, ForeignKey("backgrounds.id", ondelete="CASCADE"), nullable=True, index=True)

    # Only relevant when source_type is CLASS or SUBCLASS: the class level at
    # which the feature is gained (e.g. Extra Attack at level 5).
    level = Column(Integer, nullable=True)

    description = Column(Text, nullable=False, default="")

    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    character_class = relationship("Class")
    subclass = relationship("Subclass", back_populates="features")
    race = relationship("Race", back_populates="features")
    subrace = relationship("Subrace", back_populates="features")
    background = relationship("Background", back_populates="features")
    created_by = relationship("User")

    def __repr__(self):
        return f"<Feature(id={self.id}, name='{self.name}', source_type='{self.source_type}')>"
