"""ORM model for the reference table of class subclasses (archetypes)."""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.settings import settings


class Subclass(settings.Base):  # type: ignore
    """
    Reference table of class subclasses (archetypes), e.g. Bard → College of Valor,
    Fighter → Champion. Each subclass belongs to exactly one class and is unlocked
    at ``unlock_level`` (typically 3, sometimes 1 or 2 depending on the class).

    Features granted by the subclass are stored in the ``features`` table with
    ``source_type=SUBCLASS`` and ``subclass_id`` pointing here.
    """

    __tablename__ = "subclasses"

    id = Column(Integer, primary_key=True)

    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(100), nullable=False, index=True)
    # Human-readable grouping label shown in the UI, e.g. "Bard Colleges", "Fighter Archetypes".
    # Matches the class's own archetype grouping name; stored here for convenience.
    archetype_group_name = Column(String(100), nullable=True)
    # Class level at which the character chooses this subclass (1, 2, or 3 depending on class).
    unlock_level = Column(Integer, nullable=False, default=3)

    description = Column(Text, nullable=False, default="")
    is_homebrew = Column(Boolean, nullable=False, default=False)

    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

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
        order_by="Feature.level",
    )
    created_by = relationship("User")

    def __repr__(self):
        return f"<Subclass(id={self.id}, name='{self.name}', class_id={self.class_id})>"
