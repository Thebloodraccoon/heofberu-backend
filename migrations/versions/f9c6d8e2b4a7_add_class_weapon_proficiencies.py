"""add class weapon proficiencies

Adds the ``class_weapon_proficiencies`` sub-resource: weapon categories
(SIMPLE/MARTIAL) a class grants proficiency in, mirroring
``class_armor_proficiencies``.

Revision ID: f9c6d8e2b4a7
Revises: e8b5c7d9f1a3
Create Date: 2026-08-25 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f9c6d8e2b4a7"
down_revision: Union[str, None] = "e8b5c7d9f1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the ``weapon_proficiency`` enum and the ``class_weapon_proficiencies`` table."""

    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE weapon_proficiency AS ENUM ('SIMPLE', 'MARTIAL');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )

    op.create_table(
        "class_weapon_proficiencies",
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column(
            "weapon_category",
            postgresql.ENUM("SIMPLE", "MARTIAL", name="weapon_proficiency", create_type=False),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["class_id"], ["classes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("class_id", "weapon_category"),
    )


def downgrade() -> None:
    """Drop the table and the enum type."""

    op.drop_table("class_weapon_proficiencies")
    op.execute("DROP TYPE IF EXISTS weapon_proficiency")
