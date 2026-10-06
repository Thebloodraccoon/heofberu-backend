"""drop traits column from races

Revision ID: c3f8e2a1b5d9
Revises: 9f4c8e2a1b7d
Create Date: 2026-08-08 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3f8e2a1b5d9"
down_revision: Union[str, None] = "9f4c8e2a1b7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the free-text ``traits`` column from ``races``.

    Racial traits now live in the universal ``features`` table
    (``Feature.source_type = RACE``, linked via ``race_id``), so the
    denormalized text column is redundant and removed.
    """
    op.drop_column("races", "traits")


def downgrade() -> None:
    """Restore the ``traits`` column as NOT NULL text."""
    op.add_column("races", sa.Column("traits", sa.Text(), nullable=False, server_default=""))
