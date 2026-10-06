"""extract character backstory to its own table; add character inspiration

Revision ID: a3b4c5d6e7f8
Revises: d1e2f3a4b5c6
Create Date: 2026-08-30 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Max backstory length (chars) — mirrored from app/constants.py and the
# ORM/ schema limit. Kept literal here so the migration stays self-contained
# (matching the rest of this migrations/versions tree, which imports no app code).
BACKSTORY_MAX_LENGTH = 12000


# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the backstory table, move existing data, add inspiration, drop the old column."""

    op.create_table(
        "character_backstories",
        sa.Column(
            "character_id",
            sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.CheckConstraint(
            f"char_length(content) <= {BACKSTORY_MAX_LENGTH}",
            name="check_character_backstory_max_length",
        ),
    )

    op.execute(
        """
        INSERT INTO character_backstories (character_id, content)
        SELECT id, backstory FROM characters WHERE backstory IS NOT NULL AND backstory <> ''
        """
    )

    op.add_column("characters", sa.Column("inspiration", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("characters", "inspiration", server_default=None)

    op.drop_column("characters", "backstory")


def downgrade() -> None:
    """Reverse: re-add the backstory column, restore data, drop inspiration and the table."""

    op.add_column("characters", sa.Column("backstory", sa.Text(), nullable=False, server_default=""))

    op.execute(
        """
        UPDATE characters
        SET backstory = cb.content
        FROM character_backstories cb
        WHERE cb.character_id = characters.id
        """
    )

    op.drop_column("characters", "inspiration")
    op.drop_table("character_backstories")
