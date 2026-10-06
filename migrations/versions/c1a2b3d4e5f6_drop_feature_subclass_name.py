"""drop feature subclass name

Revision ID: c1a2b3d4e5f6
Revises: a89aff41cc17
Create Date: 2026-08-08 20:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1a2b3d4e5f6"
down_revision: Union[str, None] = "a89aff41cc17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("features", "subclass_name")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("features", sa.Column("subclass_name", sa.String(length=100), nullable=True))
