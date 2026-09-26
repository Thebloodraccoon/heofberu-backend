"""ORM model for the shared reference table of free-form tags."""

from sqlalchemy import Column, Index, Integer, String, func
from sqlalchemy.orm import relationship

from app.settings import settings


class Tag(settings.Base):  # type: ignore
    """
    Shared reference table of free-form labels, reusable across unrelated
    catalogs (races, subraces, backgrounds, articles, ...). Each catalog owns
    its own m2m link table (``race_tags``, ``subrace_tags``,
    ``background_tags``, ``article_tags``) so the FK on the "tagged" side
    stays real and typed — only the ``Tag`` dictionary itself is shared.
    """

    __tablename__ = "tags"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True, index=True)

    races = relationship("Race", secondary="race_tags", back_populates="tags")
    subraces = relationship("Subrace", secondary="subrace_tags", back_populates="tags")
    backgrounds = relationship("Background", secondary="background_tags", back_populates="tags")
    articles = relationship("Article", secondary="article_tags", back_populates="tags")

    def __repr__(self):
        return f"<Tag(id={self.id}, name='{self.name}')>"


# Case-insensitive uniqueness ("Nordavingar" == "nordavingar"); names are also trimmed at the schema layer.
Index("uq_tags_name_lower", func.lower(Tag.name), unique=True)
