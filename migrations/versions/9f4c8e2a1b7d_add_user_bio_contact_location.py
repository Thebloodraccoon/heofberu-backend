"""add bio, contact and location profile fields to users

Revision ID: 9f4c8e2a1b7d
Revises: 8e6cbf5381ba
Create Date: 2026-08-08 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f4c8e2a1b7d"
down_revision: Union[str, None] = "8e6cbf5381ba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add optional personal-cabinet fields to the users table."""
    op.add_column("users", sa.Column("bio", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("contact", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("location", sa.String(length=100), nullable=True))


def downgrade() -> None:
    """Drop the personal-cabinet fields from the users table."""
    op.drop_column("users", "location")
    op.drop_column("users", "contact")
    op.drop_column("users", "bio")
