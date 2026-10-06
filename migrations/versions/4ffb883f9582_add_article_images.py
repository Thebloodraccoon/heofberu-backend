"""add article_images

An article's ``body_markdown`` can embed several images (unlike a race/class/
subrace's single ``image_url`` column), so each gets its own row in
``article_images`` instead of a column on ``articles`` — independently
uploadable/captioned/reordered/deleted. Matches
``app/models/articles/article_image_model.py``.

Revision ID: 4ffb883f9582
Revises: 47437cd77998
Create Date: 2026-09-21 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4ffb883f9582"
down_revision: Union[str, None] = "47437cd77998"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "article_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("caption", sa.String(length=300), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_article_images_article_id"), "article_images", ["article_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f("ix_article_images_article_id"), table_name="article_images")
    op.drop_table("article_images")
