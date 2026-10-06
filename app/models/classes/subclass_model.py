"""ORM model for the reference table of class subclasses (archetypes)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.classes.class_model import Class
    from app.models.features.feature_model import Feature


class Subclass(Base):
    """
    Reference table of class subclasses (archetypes), e.g. Bard → College of Valor,
    Fighter → Champion. Each subclass belongs to exactly one class; no level at
    which it unlocks is stored.

    Features granted by the subclass are stored in the ``features`` table with
    ``source_type=SUBCLASS`` and ``subclass_id`` pointing here.
    """

    __tablename__ = "subclasses"

    id: Mapped[int] = mapped_column(primary_key=True)

    # No own index: ``uq_subclass_class_id_name`` already leads with ``class_id``.
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))

    name: Mapped[str] = mapped_column(String(100), index=True)

    description: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str | None] = mapped_column(String(512))

    __table_args__ = (UniqueConstraint("class_id", "name", name="uq_subclass_class_id_name"),)

    character_class: Mapped[Class] = relationship(back_populates="subclasses")
    features: Mapped[list[Feature]] = relationship(
        back_populates="subclass",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Feature.id",
    )

    def __repr__(self) -> str:
        return f"<Subclass(id={self.id}, name='{self.name}', class_id={self.class_id})>"
