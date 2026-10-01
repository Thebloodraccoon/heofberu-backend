"""feature ability increases; drop class_primary_abilities and subclass archetype_group_name

Revision ID: c5d9e8f2a4b7
Revises: b8e2f4a6c9d1
Create Date: 2026-08-25 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c5d9e8f2a4b7"
down_revision: Union[str, None] = "b8e2f4a6c9d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ability_score_enum = postgresql.ENUM(
    "STR",
    "DEX",
    "CON",
    "INT",
    "WIS",
    "CHA",
    name="ability_score",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""

    # 1. Fixed ability-score effects of features (counted while the
    #    feature is granted to a character). new_cap raises the standard
    #    20 cap for that ability (e.g. Primal Champion -> 24).
    op.create_table(
        "feature_ability_increases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=False),
        sa.Column("ability", ability_score_enum, nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("new_cap", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_feature_ability_increases_feature_id"),
        "feature_ability_increases",
        ["feature_id"],
        unique=False,
    )

    # 2. Drop the dead class primary-abilities reference table.
    op.drop_table("class_primary_abilities")

    # 3. Drop the UI-only archetype grouping label from subclasses.
    op.drop_column("subclasses", "archetype_group_name")


def downgrade() -> None:
    """Downgrade schema."""

    op.add_column(
        "subclasses",
        sa.Column("archetype_group_name", sa.String(length=100), nullable=True),
    )

    op.create_table(
        "class_primary_abilities",
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("ability", ability_score_enum, nullable=False),
        sa.ForeignKeyConstraint(["class_id"], ["classes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("class_id", "ability"),
    )

    op.drop_index(op.f("ix_feature_ability_increases_feature_id"), table_name="feature_ability_increases")
    op.drop_table("feature_ability_increases")
