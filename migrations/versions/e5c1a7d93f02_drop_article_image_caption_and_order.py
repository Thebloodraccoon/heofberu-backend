"""drop article image caption and sort_order

Article images are shown only where ``body_markdown`` embeds them
(``![alt](url)``) — alt text and order live in the markdown, so the gallery
metadata columns ``article_images.caption`` / ``sort_order`` are dropped.

Revision ID: e5c1a7d93f02
Revises: d2b8f6c41a97
Create Date: 2026-09-26 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5c1a7d93f02"
down_revision: Union[str, None] = "d2b8f6c41a97"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.drop_column("article_images", "sort_order")
    op.drop_column("article_images", "caption")


def downgrade() -> None:
    """Downgrade schema (captions/order come back empty)."""

    op.add_column("article_images", sa.Column("caption", sa.String(length=300), nullable=True))
    op.add_column("article_images", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))
