"""ORM models for a public campaign (preset/announcement), its article links and tags."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Table, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import PublicCampaignStatus
from app.models.enums import PublicCampaignStatusType
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.articles.article_model import Article
    from app.models.campaigns.campaign_model import Campaign
    from app.models.tag_model import Tag
    from app.models.user_model import User

# public_campaigns <-> tags (shared Tag dictionary)
public_campaign_tags = Table(
    "public_campaign_tags",
    Base.metadata,
    Column("public_campaign_id", Integer, ForeignKey("public_campaigns.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="RESTRICT"), primary_key=True),
    Index("ix_public_campaign_tags_tag_id", "tag_id"),
)


class PublicCampaign(Base):
    """
    A public campaign: the pitch ("зазывалка") and description any GM can start a game campaign from.

    Readable by everyone once ``PUBLISHED`` (``:::gm`` blocks stripped for non-GMs). Game campaigns link to it
    (``campaigns.public_campaign_id``); their reviews and the characters whose owners allowed it are shown here.
    Article links are for GMs only.
    """

    __tablename__ = "public_campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(220), unique=True, index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)

    title: Mapped[str] = mapped_column(String(200))
    pitch: Mapped[str] = mapped_column(String(500), default="")
    description_markdown: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[PublicCampaignStatus] = mapped_column(
        PublicCampaignStatusType, default=PublicCampaignStatus.DRAFT, server_default="DRAFT", index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # The catalog's ``?q=`` is ``ILIKE '%x%'`` on title OR pitch: one trigram index each, combined by a BitmapOr
    # (pg_trgm is installed by migration 0001).
    __table_args__ = (
        Index(
            "ix_public_campaigns_title_trgm", "title", postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"}
        ),
        Index(
            "ix_public_campaigns_pitch_trgm", "pitch", postgresql_using="gin", postgresql_ops={"pitch": "gin_trgm_ops"}
        ),
    )

    # Not eager by default: repositories load what each response needs (``selectinload``/columns).
    author: Mapped[User | None] = relationship(foreign_keys=[author_id])
    tags: Mapped[list[Tag]] = relationship(secondary=public_campaign_tags, order_by="Tag.name")
    articles: Mapped[list[PublicCampaignArticle]] = relationship(
        back_populates="public_campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PublicCampaignArticle.position",
    )
    campaigns: Mapped[list[Campaign]] = relationship(back_populates="public_campaign", passive_deletes=True)

    def __repr__(self) -> str:
        return f"<PublicCampaign(id={self.id}, slug='{self.slug}', status={self.status})>"


class PublicCampaignArticle(Base):
    """A knowledge-base article a public campaign points GMs to (ordered, with an optional note)."""

    __tablename__ = "public_campaign_articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_campaign_id: Mapped[int] = mapped_column(ForeignKey("public_campaigns.id", ondelete="CASCADE"))
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(default=0)
    note: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (UniqueConstraint("public_campaign_id", "article_id", name="uq_public_campaign_articles_article"),)

    public_campaign: Mapped[PublicCampaign] = relationship(back_populates="articles")
    article: Mapped[Article] = relationship()

    def __repr__(self) -> str:
        return f"<PublicCampaignArticle(public_campaign_id={self.public_campaign_id}, article_id={self.article_id})>"
