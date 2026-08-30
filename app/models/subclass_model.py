"""ORM model for the reference table of class subclasses (archetypes)."""

from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.settings import settings


class Subclass(settings.Base):  # type: ignore
    """
    Reference table of class subclasses (archetypes), e.g. Bard → College of Valor,
    Fighter → Champion. Each subclass belongs to exactly one class and is unlocked
    at a class-specific level (typically 3, sometimes 1 or 2 depending on the class).

    Features granted by the subclass are stored in the ``features`` table with
    ``source_type=SUBCLASS`` and ``subclass_id`` pointing here.
    """

    __tablename__ = "subclasses"

    id = Column(Integer, primary_key=True)

    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(100), nullable=False, index=True)

    description = Column(Text, nullable=False, default="")

    __table_args__ = (
        # A class cannot have two subclasses with the same name.
        UniqueConstraint("class_id", "name", name="uq_subclass_class_id_name"),
    )

    character_class = relationship("Class", back_populates="subclasses")
    # All features granted by this subclass across all levels.
    features = relationship(
        "Feature",
        back_populates="subclass",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Feature.id",
    )

    def __repr__(self):
        return f"<Subclass(id={self.id}, name='{self.name}', class_id={self.class_id})>"
