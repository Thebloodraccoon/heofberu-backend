"""add character personality fields

Revision ID: b7c2d9e4f1a8
Revises: af6347715f5e
Create Date: 2026-08-21 15:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c2d9e4f1a8"
down_revision: Union[str, None] = "af6347715f5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    for column in ("personality_traits", "ideals", "bonds", "flaws"):
        op.add_column("characters", sa.Column(column, sa.Text(), nullable=False, server_default=sa.text("''")))


def downgrade() -> None:
    """Downgrade schema."""
    for column in ("personality_traits", "ideals", "bonds", "flaws"):
        op.drop_column("characters", column)
