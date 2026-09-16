"""ORM model for the reference table of subrace cultural/regional tags."""

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.settings import settings


class SubraceTag(settings.Base):  # type: ignore
    """
    Reference table of cultural/regional tags for subraces
    (e.g. "Sutrice", "Nordavingar", "Great Steppe").

    A tag is a cross-cutting classification independent of the race hierarchy:
    subraces belonging to different races can share a tag, and a single
    subrace can carry several tags (m2m via ``subrace_tag_links``).

    NOT IMPLEMENTED at the API layer yet: several subraces sharing one tag
    raises open questions (e.g. what a shared tag should mean/do for
    gameplay) that need more design before exposing read/write endpoints.
    The model/table exist; wiring an ``app/features`` layer on top is
    deferred to a separate PR.
    """

    __tablename__ = "subrace_tags"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True, index=True)

    subraces = relationship(
        "Subrace",
        secondary="subrace_tag_links",
        back_populates="tags",
    )

    def __repr__(self):
        return f"<SubraceTag(id={self.id}, name='{self.name}')>"
