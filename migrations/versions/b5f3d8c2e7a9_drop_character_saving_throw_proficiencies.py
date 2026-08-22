"""drop character_saving_throw_proficiencies (saving throws now come from the class)

Revision ID: b5f3d8c2e7a9
Revises: c4d7e1a9f3b2
Create Date: 2026-08-21 20:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b5f3d8c2e7a9"
down_revision: Union[str, None] = "c4d7e1a9f3b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.drop_table("character_saving_throw_proficiencies")


def downgrade() -> None:
    """Downgrade schema."""

    op.create_table(
        "character_saving_throw_proficiencies",
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column(
            "ability",
            postgresql.ENUM("STR", "DEX", "CON", "INT", "WIS", "CHA", name="ability_score", create_type=False),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("character_id", "ability"),
    )
