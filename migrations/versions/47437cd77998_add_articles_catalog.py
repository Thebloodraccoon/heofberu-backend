"""add articles catalog

New world-lore catalog: ``articles`` (polymorphic — ``article_type`` is an
open string list, see ``ARTICLE_TYPES`` in ``app/constants.py``, not a
Postgres ENUM, so new article types never need a migration),
``article_relations`` (typed directed graph between articles for everything
that doesn't fit the ``parent_id``/``path`` hierarchy — membership, kinship,
feud, mentions; see ``RELATION_TYPES``) and ``article_tags`` (m2m link into
the shared ``tags`` dictionary from ``a031c08480da``).

``path`` uses the Postgres ``ltree`` extension (not installed by any
existing migration — installed here, first use) for efficient
ancestor/descendant queries over the navigation tree.

Out of scope here (left for later phases, per ``app/models/articles/``):
``search_vector`` (generated tsvector column + GIN index) and any
``reviewed_by_id`` review-flow wiring.

Revision ID: 47437cd77998
Revises: a031c08480da
Create Date: 2026-09-21 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy_utils import LtreeType


# revision identifiers, used by Alembic.
revision: str = "47437cd77998"
down_revision: Union[str, None] = "a031c08480da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

article_status_enum = postgresql.ENUM(
    "DRAFT",
    "IN_REVIEW",
    "PUBLISHED",
    "ARCHIVED",
    name="article_status",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""

    op.execute("CREATE EXTENSION IF NOT EXISTS ltree;")
    article_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=220), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("excerpt", sa.String(length=500), nullable=True),
        sa.Column("body_markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("article_type", sa.String(length=50), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("path", LtreeType(), nullable=True),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            postgresql.ENUM("DRAFT", "IN_REVIEW", "PUBLISHED", "ARCHIVED", name="article_status", create_type=False),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["articles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_articles_slug"), "articles", ["slug"], unique=True)
    op.create_index(op.f("ix_articles_title"), "articles", ["title"], unique=False)
    op.create_index(op.f("ix_articles_article_type"), "articles", ["article_type"], unique=False)
    op.create_index(op.f("ix_articles_parent_id"), "articles", ["parent_id"], unique=False)
    op.create_index(op.f("ix_articles_path"), "articles", ["path"], unique=False)
    op.create_index(op.f("ix_articles_status"), "articles", ["status"], unique=False)
    op.create_index(op.f("ix_articles_author_id"), "articles", ["author_id"], unique=False)

    op.create_table(
        "article_relations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("from_article_id", sa.Integer(), nullable=False),
        sa.Column("to_article_id", sa.Integer(), nullable=False),
        sa.Column("relation_type", sa.String(length=50), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["from_article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "from_article_id", "to_article_id", "relation_type", name="uq_article_relation"
        ),
    )
    op.create_index(
        op.f("ix_article_relations_from_article_id"), "article_relations", ["from_article_id"], unique=False
    )
    op.create_index(
        op.f("ix_article_relations_to_article_id"), "article_relations", ["to_article_id"], unique=False
    )
    op.create_index(
        op.f("ix_article_relations_relation_type"), "article_relations", ["relation_type"], unique=False
    )

    op.create_table(
        "article_tags",
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("article_id", "tag_id"),
    )
    op.create_index(op.f("ix_article_tags_tag_id"), "article_tags", ["tag_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f("ix_article_tags_tag_id"), table_name="article_tags")
    op.drop_table("article_tags")

    op.drop_index(op.f("ix_article_relations_relation_type"), table_name="article_relations")
    op.drop_index(op.f("ix_article_relations_to_article_id"), table_name="article_relations")
    op.drop_index(op.f("ix_article_relations_from_article_id"), table_name="article_relations")
    op.drop_table("article_relations")

    op.drop_index(op.f("ix_articles_author_id"), table_name="articles")
    op.drop_index(op.f("ix_articles_status"), table_name="articles")
    op.drop_index(op.f("ix_articles_path"), table_name="articles")
    op.drop_index(op.f("ix_articles_parent_id"), table_name="articles")
    op.drop_index(op.f("ix_articles_article_type"), table_name="articles")
    op.drop_index(op.f("ix_articles_title"), table_name="articles")
    op.drop_index(op.f("ix_articles_slug"), table_name="articles")
    op.drop_table("articles")

    article_status_enum.drop(op.get_bind(), checkfirst=True)

    op.execute("DROP EXTENSION IF EXISTS ltree;")
