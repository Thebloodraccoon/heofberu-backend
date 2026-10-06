"""add character_max_levels (GM-set level-up cap, backfilled to current level)

Revision ID: e2a9f4b7c6d1
Revises: b5f3d8c2e7a9
Create Date: 2026-08-22 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2a9f4b7c6d1"
down_revision: Union[str, None] = "b5f3d8c2e7a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "character_max_levels",
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("max_level", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("character_id"),
        sa.CheckConstraint("max_level >= 1 AND max_level <= 20", name="check_character_max_level_range"),
    )

    # Existing characters keep their current level as the cap: they cannot
    # level up past it until a GM raises the maximum.
    op.execute("INSERT INTO character_max_levels (character_id, max_level) SELECT id, level FROM characters")


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_table("character_max_levels")
