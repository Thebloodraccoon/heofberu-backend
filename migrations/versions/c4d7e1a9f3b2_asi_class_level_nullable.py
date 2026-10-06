"""make character_asi_choices.class_level nullable (GM adjustments)

Revision ID: c4d7e1a9f3b2
Revises: 6fa86eefd557
Create Date: 2026-08-21 19:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c4d7e1a9f3b2"
down_revision: Union[str, None] = "6fa86eefd557"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.alter_column("character_asi_choices", "class_level", existing_type=sa.INTEGER(), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""

    op.alter_column("character_asi_choices", "class_level", existing_type=sa.INTEGER(), nullable=False)
