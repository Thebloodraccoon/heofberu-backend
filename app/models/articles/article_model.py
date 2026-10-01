"""ORM model for world-lore articles (global lore down to a single location/faction/NPC)."""

from sqlalchemy import Column, Computed, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import deferred, relationship
from sqlalchemy_utils import LtreeType

from app.constants import ARTICLE_GM_BLOCK_SQL_PATTERN, ArticleStatus, ArticleVisibility
from app.models.enums import ArticleStatusType, ArticleVisibilityType
from app.settings import settings

#: A GM block that contains another ``:::`` container: from ``:::gm`` to the end of the text (fail closed, the flat
#: pattern would close the block at the inner ``:::``). Keep equal to ``NESTED_GM_BLOCK_SQL_PATTERN`` in
#: ``app/features/articles/secrets.py``.
NESTED_GM_BLOCK_SQL_PATTERN = r"(?i):::gm(?:(?!:::).)*:::[a-z].*"


def _public_sql(column: str) -> str:
    """``column`` without GM blocks: nested ones first (to the end of the text), then the flat ``:::gm ... :::``."""

    without_nested = f"regexp_replace(coalesce({column}, ''), '{NESTED_GM_BLOCK_SQL_PATTERN}', ' ', 'g')"
    return f"regexp_replace({without_nested}, '{ARTICLE_GM_BLOCK_SQL_PATTERN}', ' ', 'g')"


PUBLIC_BODY_SQL = _public_sql("body_markdown")
PUBLIC_EXCERPT_SQL = _public_sql("excerpt")


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


_PUBLIC_ROW = text("status = 'PUBLISHED' AND visibility = 'PUBLIC'")


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
        # Non-GM listings (published + public only), sorted by title or by date: partial indexes serve the sort.
        Index("ix_articles_public_title", "title", "id", postgresql_where=_PUBLIC_ROW),
        Index(
            "ix_articles_public_published",
            text("COALESCE(published_at, created_at) DESC"),
            text("id DESC"),
            postgresql_where=_PUBLIC_ROW,
        ),
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
    reviewed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Generated columns (never written by the app): weighted title > excerpt > body, Russian + simple configs.
    # deferred: never in a response, no reason to load them on every select(Article).
    search_vector = deferred(Column(TSVECTOR, Computed(SEARCH_VECTOR_SQL, persisted=True), nullable=True))
    search_vector_gm = deferred(Column(TSVECTOR, Computed(SEARCH_VECTOR_GM_SQL, persisted=True), nullable=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)

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
