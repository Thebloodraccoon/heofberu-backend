"""add spell_subclasses and spell_subraces availability tables

Revision ID: f7c1b8d3a5e2
Revises: e2a9f4b7c6d1
Create Date: 2026-08-22 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7c1b8d3a5e2"
down_revision: Union[str, None] = "e2a9f4b7c6d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "spell_subclasses",
        sa.Column("spell_id", sa.Integer(), nullable=False),
        sa.Column("subclass_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["spell_id"], ["spells.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subclass_id"], ["subclasses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("spell_id", "subclass_id"),
    )
    op.create_table(
        "spell_subraces",
        sa.Column("spell_id", sa.Integer(), nullable=False),
        sa.Column("subrace_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["spell_id"], ["spells.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subrace_id"], ["subraces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("spell_id", "subrace_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_table("spell_subraces")
    op.drop_table("spell_subclasses")
