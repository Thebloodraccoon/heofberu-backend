"""ORM model for world-lore articles (global lore down to a single location/faction/NPC)."""

from sqlalchemy import Column, Computed, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import deferred, relationship
from sqlalchemy_utils import LtreeType

from app.constants import (
    ARTICLE_GM_BLOCK_SQL_PATTERN,
    ArticleStatus,
    ArticleVisibility,
    is_article_publicly_visible,
)
from app.models.enums import ArticleStatusType, ArticleVisibilityType
from app.settings import settings


PUBLIC_BODY_SQL = f"regexp_replace(coalesce(body_markdown, ''), '{ARTICLE_GM_BLOCK_SQL_PATTERN}', ' ', 'g')"
PUBLIC_EXCERPT_SQL = f"regexp_replace(coalesce(excerpt, ''), '{ARTICLE_GM_BLOCK_SQL_PATTERN}', ' ', 'g')"


def _search_vector_sql(excerpt_sql: str, body_sql: str) -> str:
    """Weighted tsvector: title A > ``excerpt_sql`` B > ``body_sql`` C, ``russian`` + ``simple`` configs."""

    return (
        "setweight(to_tsvector('russian', coalesce(title, '')), 'A') || "
        "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
        f"setweight(to_tsvector('russian', {excerpt_sql}), 'B') || "
        f"setweight(to_tsvector('russian', {body_sql}), 'C') || "
        f"setweight(to_tsvector('simple', {body_sql}), 'C')"
    )


#: Non-GM search: GM-only blocks are stripped from the excerpt and body before indexing.
SEARCH_VECTOR_SQL = _search_vector_sql(PUBLIC_EXCERPT_SQL, PUBLIC_BODY_SQL)
#: GM search: the full excerpt and body, secrets included.
SEARCH_VECTOR_GM_SQL = _search_vector_sql("coalesce(excerpt, '')", "coalesce(body_markdown, '')")


class Article(settings.Base):  # type: ignore
    """
    Полиморфная статья о мире: от глобального лора до конкретной
    локации/фракции/НПС. ``article_type`` — открытый список (см.
    ``ARTICLE_TYPES``), не Postgres ENUM: новый тип статьи не требует
    миграции. ``parent_id``/``path`` — единственная иерархическая
    "вертикаль" (навигация/URL); всё остальное — через ``ArticleRelation``.
    """

    __tablename__ = "articles"
    __table_args__ = (
        # ltree ``<@``/``@>`` (tree queries) need GiST; B-tree can't serve them.
        Index("ix_articles_path", "path", postgresql_using="gist"),
        Index("ix_articles_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_articles_search_vector_gm", "search_vector_gm", postgresql_using="gin"),
        Index("ix_articles_title_trgm", "title", postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"}),
    )

    id = Column(Integer, primary_key=True)

    slug = Column(String(220), nullable=False, unique=True, index=True)
    title = Column(String(200), nullable=False, index=True)
    excerpt = Column(String(500), nullable=True)
    body_markdown = Column(Text, nullable=False, default="")

    article_type = Column(String(50), nullable=False, index=True)
    subtype_id = Column(Integer, ForeignKey("article_subtypes.id", ondelete="SET NULL"), nullable=True, index=True)

    parent_id = Column(Integer, ForeignKey("articles.id", ondelete="SET NULL"), nullable=True, index=True)
    path = Column(LtreeType, nullable=True)


    status = Column(ArticleStatusType, nullable=False, default=ArticleStatus.DRAFT, index=True)
    visibility = Column(
        ArticleVisibilityType, nullable=False, default=ArticleVisibility.PUBLIC, server_default="PUBLIC", index=True
    )
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reviewed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # фаза 3

    # Generated columns (never written by the app): weighted title > excerpt > body, Russian + simple configs.
    # deferred: never in a response, no reason to load them on every select(Article).
    search_vector = deferred(Column(TSVECTOR, Computed(SEARCH_VECTOR_SQL, persisted=True), nullable=True))
    search_vector_gm = deferred(Column(TSVECTOR, Computed(SEARCH_VECTOR_GM_SQL, persisted=True), nullable=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)

    parent = relationship("Article", remote_side=[id], back_populates="children")
    children = relationship("Article", back_populates="parent")
    author = relationship("User", foreign_keys=[author_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])
    # Many-to-one, always needed in responses (incl. tree/relation briefs): joined-loaded, never lazy in async.
    subtype = relationship("ArticleSubtype", lazy="joined")
    tags = relationship("Tag", secondary="article_tags", back_populates="articles", order_by="Tag.name")
    images = relationship(
        "ArticleImage",
        back_populates="article",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ArticleImage.id",
    )

    def __repr__(self):
        return f"<Article(id={self.id}, slug='{self.slug}', type='{self.article_type}')>"

    @property
    def is_publicly_visible(self) -> bool:
        """Whether a non-GM reader may see this article (published and public)."""

        return is_article_publicly_visible(self.status, self.visibility)
