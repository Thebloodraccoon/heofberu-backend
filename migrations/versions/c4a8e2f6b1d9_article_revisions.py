"""article revisions (version history)

- ``articles.version`` (NOT NULL, default 1): content version, +1 per saved content change;
- ``article_revisions``: one snapshot of the content per version, unique per (``article_id``, ``version``),
  deleted with the article (``ON DELETE CASCADE``), ``editor_id`` kept as ``SET NULL`` when the user is deleted.

Every existing article gets its current content as version 1 (editor = its author, when known).

Revision ID: c4a8e2f6b1d9
Revises: a6d1f3b5c7e9
Create Date: 2026-10-02 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c4a8e2f6b1d9"
down_revision: Union[str, None] = "a6d1f3b5c7e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column("articles", sa.Column("version", sa.Integer(), server_default="1", nullable=False))

    op.create_table(
        "article_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("excerpt", sa.String(length=500), nullable=True),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("article_type", sa.String(length=50), nullable=False),
        sa.Column("subtype_id", sa.Integer(), nullable=True),
        sa.Column(
            "visibility",
            postgresql.ENUM("PUBLIC", "GM_ONLY", name="article_visibility", create_type=False),
            nullable=False,
        ),
        sa.Column("editor_id", sa.Integer(), nullable=True),
        sa.Column("change_note", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["editor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("article_id", "version", name="uq_article_revisions_article_version"),
    )
    op.create_index(op.f("ix_article_revisions_editor_id"), "article_revisions", ["editor_id"], unique=False)

    op.execute(
        """
        INSERT INTO article_revisions
            (article_id, version, title, excerpt, body_markdown, article_type, subtype_id, visibility,
             editor_id, change_note, created_at)
        SELECT id, 1, title, excerpt, body_markdown, article_type, subtype_id, visibility,
               author_id, 'Initial version (backfilled)', COALESCE(updated_at, created_at)
        FROM articles
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f("ix_article_revisions_editor_id"), table_name="article_revisions")
    op.drop_table("article_revisions")
    op.drop_column("articles", "version")
