"""ORM model for the shared reference table of free-form tags."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.articles.article_model import Article
    from app.models.backgrounds.background_model import Background
    from app.models.races.race_model import Race
    from app.models.races.subrace_model import Subrace


class Tag(Base):
    """
    Shared reference table of free-form labels, reusable across unrelated
    catalogs (races, subraces, backgrounds, articles, ...). Each catalog owns
    its own m2m link table (``race_tags``, ``subrace_tags``,
    ``background_tags``, ``article_tags``) so the FK on the "tagged" side
    stays real and typed — only the ``Tag`` dictionary itself is shared.
    """

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))  # unique ignoring case: ``uq_tags_name_lower`` below

    races: Mapped[list[Race]] = relationship(secondary="race_tags", back_populates="tags")
    subraces: Mapped[list[Subrace]] = relationship(secondary="subrace_tags", back_populates="tags")
    backgrounds: Mapped[list[Background]] = relationship(secondary="background_tags", back_populates="tags")
    articles: Mapped[list[Article]] = relationship(secondary="article_tags", back_populates="tags")

    def __repr__(self) -> str:
        return f"<Tag(id={self.id}, name='{self.name}')>"


# Case-insensitive uniqueness ("Nordavingar" == "nordavingar"); names are also trimmed at the schema layer.
Index("uq_tags_name_lower", func.lower(Tag.name), unique=True)
