"""split user contact into phone/discord/telegram and drop location

Refactors the user's profile contact fields:

- the single generic ``contact`` column is split into three dedicated
  ones: ``phone``, ``discord`` and ``telegram``. Existing ``contact``
  data is preserved into ``discord`` (the most common free-text handle)
  rather than discarded;
- the ``location`` column is removed.

Revision ID: f2a9c7d3b5e1
Revises: e3d5f7a9b2c4
Create Date: 2026-08-31 12:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2a9c7d3b5e1"
down_revision: Union[str, None] = "e3d5f7a9b2c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Split ``contact`` into three fields and drop ``location``."""

    op.add_column("users", sa.Column("phone", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("discord", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("telegram", sa.String(length=100), nullable=True))

    op.execute("UPDATE users SET discord = contact WHERE contact IS NOT NULL")

    op.drop_column("users", "contact")
    op.drop_column("users", "location")


def downgrade() -> None:
    """Re-merge the fields back into ``contact`` and restore ``location``."""

    op.add_column("users", sa.Column("contact", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("location", sa.String(length=100), nullable=True))

    op.execute("UPDATE users SET contact = discord WHERE discord IS NOT NULL")

    op.drop_column("users", "telegram")
    op.drop_column("users", "discord")
    op.drop_column("users", "phone")
