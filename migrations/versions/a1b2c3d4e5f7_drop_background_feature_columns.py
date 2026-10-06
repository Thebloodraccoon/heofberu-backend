"""drop background feature columns

Revision ID: a1b2c3d4e5f7
Revises: d2e3f4a5b6c7
Create Date: 2026-08-08 21:15:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Background "features" now live in the ``features`` table as
    # BACKGROUND-source rows (features.background_id), created nested in
    # the same request as the background. The free-text columns are gone.
    op.drop_column("backgrounds", "feature_name")
    op.drop_column("backgrounds", "feature_description")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "backgrounds",
        sa.Column("feature_description", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "backgrounds",
        sa.Column("feature_name", sa.String(length=200), nullable=False, server_default=""),
    )
