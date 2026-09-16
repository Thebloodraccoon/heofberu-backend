"""drop features.is_repeatable

The ``is_repeatable`` column on ``features`` (whether a feat may be taken
more than once) was never actually consumed anywhere — no character-grant
logic read it, and it was missing entirely from the ``/feats`` API despite
being settable through the generic ``/features`` endpoint for
``source_type=FEAT`` rows. Removed rather than half-wired; the "repeatable
feat" mechanic can be reintroduced properly in a future PR if/when needed.

Revision ID: f0168d7c8559
Revises: f3a5c7e9b1d4
Create Date: 2026-09-11 19:27:16.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f0168d7c8559"
down_revision: Union[str, None] = "f3a5c7e9b1d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("features", "is_repeatable")


def downgrade() -> None:
    op.add_column(
        "features",
        sa.Column("is_repeatable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("features", "is_repeatable", server_default=None)
