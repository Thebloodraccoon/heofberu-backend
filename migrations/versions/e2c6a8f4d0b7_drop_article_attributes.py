"""drop article attributes

``articles.attributes`` (free-form JSONB) is dropped — unused, all article content lives
in ``body_markdown``. Also drops ``gm_attributes`` if an earlier draft of
``d8b4f0a2c6e9`` already created it on a dev database.

Revision ID: e2c6a8f4d0b7
Revises: d8b4f0a2c6e9
Create Date: 2026-09-30 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e2c6a8f4d0b7"
down_revision: Union[str, None] = "d8b4f0a2c6e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS gm_attributes")
    op.drop_column("articles", "attributes")


def downgrade() -> None:
    """Downgrade schema."""

    op.add_column(
        "articles",
        sa.Column("attributes", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
