"""ORM model for the GM-managed dictionary of article subtypes."""

from sqlalchemy import Column, Index, Integer, String, func

from app.settings import settings


class ArticleSubtype(settings.Base):  # type: ignore
    """
    A refinement of one ``article_type`` (location → «таверна», «город», «данж»).

    A subtype belongs to exactly one ``article_type``, fixed at creation; an article may
    only use a subtype of its own type. Names are unique per type, ignoring case.
    """

    __tablename__ = "article_subtypes"

    id = Column(Integer, primary_key=True)
    article_type = Column(String(50), nullable=False, index=True)
    name = Column(String(50), nullable=False)

    def __repr__(self):
        return f"<ArticleSubtype(id={self.id}, article_type='{self.article_type}', name='{self.name}')>"


Index("uq_article_subtypes_type_name_lower", ArticleSubtype.article_type, func.lower(ArticleSubtype.name), unique=True)
