"""session_reviews.hidden_at: founder moderation of session reviews (same as campaign_reviews.hidden_at)

Revision ID: b3d9f1a6c8e2
Revises: a7c3e5f9b1d4
Create Date: 2026-10-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3d9f1a6c8e2"
down_revision: Union[str, None] = "a7c3e5f9b1d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("session_reviews", sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("session_reviews", "hidden_at")
