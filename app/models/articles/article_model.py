"""ORM model for world-lore articles (global lore down to a single location/faction/NPC)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Computed, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy_utils import Ltree, LtreeType

from app.constants import ARTICLE_GM_BLOCK_SQL_PATTERN, ArticleStatus, ArticleVisibility
from app.models.enums import ArticleStatusType, ArticleVisibilityType
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.articles.article_image_model import ArticleImage
    from app.models.articles.article_subtype_model import ArticleSubtype
    from app.models.tag_model import Tag

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


class Article(Base):
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

    id: Mapped[int] = mapped_column(primary_key=True)

    slug: Mapped[str] = mapped_column(String(220), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    excerpt: Mapped[str | None] = mapped_column(String(500))
    body_markdown: Mapped[str] = mapped_column(Text, default="")

    article_type: Mapped[str] = mapped_column(String(50), index=True)
    subtype_id: Mapped[int | None] = mapped_column(ForeignKey("article_subtypes.id", ondelete="SET NULL"), index=True)

    parent_id: Mapped[int | None] = mapped_column(ForeignKey("articles.id", ondelete="SET NULL"), index=True)
    path: Mapped[Ltree | None] = mapped_column(LtreeType)

    status: Mapped[ArticleStatus] = mapped_column(ArticleStatusType, default=ArticleStatus.DRAFT, index=True)
    visibility: Mapped[ArticleVisibility] = mapped_column(
        ArticleVisibilityType, default=ArticleVisibility.PUBLIC, server_default="PUBLIC", index=True
    )
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)

    # Generated columns (never written by the app): weighted title > excerpt > body, Russian + simple configs.
    # deferred: never in a response, no reason to load them on every select(Article).
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed(SEARCH_VECTOR_SQL, persisted=True), deferred=True
    )
    search_vector_gm: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed(SEARCH_VECTOR_GM_SQL, persisted=True), deferred=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Content version, +1 per saved change of the content fields; mirrored by ``ArticleRevision.version``.
    version: Mapped[int] = mapped_column(default=1, server_default="1")

    # Many-to-one, always needed in responses (incl. tree/relation briefs): joined-loaded, never lazy in async.
    subtype: Mapped[ArticleSubtype | None] = relationship(lazy="joined")
    tags: Mapped[list[Tag]] = relationship(secondary="article_tags", back_populates="articles", order_by="Tag.name")
    images: Mapped[list[ArticleImage]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ArticleImage.id",
    )

    def __repr__(self) -> str:
        return f"<Article(id={self.id}, slug='{self.slug}', type='{self.article_type}')>"
