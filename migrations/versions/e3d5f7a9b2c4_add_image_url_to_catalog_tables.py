"""add image_url to catalog reference tables

Adds a nullable ``image_url`` column to ``races``, ``subraces``,
``classes`` and ``subclasses`` so each catalog row can carry its own
public image URL (managed via the per-catalog image endpoints backed by
Supabase Storage, ``app.core.storage``).

Revision ID: e3d5f7a9b2c4
Revises: a3b4c5d6e7f8
Create Date: 2026-08-31 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e3d5f7a9b2c4"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the nullable ``image_url`` column to the four catalog tables."""

    for table in ("races", "subraces", "classes", "subclasses"):
        op.add_column(table, sa.Column("image_url", sa.String(length=512), nullable=True))


def downgrade() -> None:
    """Drop the ``image_url`` column from the four catalog tables."""

    for table in ("races", "subraces", "classes", "subclasses"):
        op.drop_column(table, "image_url")
