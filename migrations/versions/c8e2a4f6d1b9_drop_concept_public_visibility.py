"""characters.public_visibility: drop the CONCEPT level (only HIDDEN / FULL remain)

A ``CONCEPT`` character becomes ``HIDDEN``: its owner never agreed to show the full card.

Revision ID: c8e2a4f6d1b9
Revises: b3d9f1a6c8e2
Create Date: 2026-10-19 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c8e2a4f6d1b9"
down_revision: Union[str, None] = "b3d9f1a6c8e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE characters SET public_visibility = 'HIDDEN' WHERE public_visibility = 'CONCEPT'")


def downgrade() -> None:
    # Which characters were CONCEPT is not kept; they stay HIDDEN.
    pass
