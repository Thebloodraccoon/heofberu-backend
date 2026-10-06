"""convert character inspiration from a boolean to a 0-13 point pool

5e's plain per-session boolean is replaced with a stockpile the GM can
grant multiple points into and the player spends down over time. An
existing ``True`` maps to 1 point, ``False`` to 0.

Revision ID: b3f6a2c8d4e1
Revises: f2a9c7d3b5e1
Create Date: 2026-09-06 17:15:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3f6a2c8d4e1"
down_revision: Union[str, None] = "f2a9c7d3b5e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert ``inspiration`` to an integer and cap it at [0, 13]."""

    op.alter_column(
        "characters",
        "inspiration",
        type_=sa.Integer(),
        postgresql_using="inspiration::int",
        nullable=False,
        server_default="0",
    )
    op.alter_column("characters", "inspiration", server_default=None)
    op.create_check_constraint("check_inspiration_range", "characters", "inspiration >= 0 AND inspiration <= 13")


def downgrade() -> None:
    """Revert ``inspiration`` to a boolean (any positive count becomes ``True``)."""

    op.drop_constraint("check_inspiration_range", "characters", type_="check")
    op.alter_column(
        "characters",
        "inspiration",
        type_=sa.Boolean(),
        postgresql_using="inspiration > 0",
        nullable=False,
        server_default=sa.false(),
    )
    op.alter_column("characters", "inspiration", server_default=None)
