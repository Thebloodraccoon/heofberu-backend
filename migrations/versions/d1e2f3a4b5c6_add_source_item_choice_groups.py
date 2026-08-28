"""add source_item_choice_groups and source_item_choice_options tables

Revision ID: d1e2f3a4b5c6
Revises: c5d9e8f2a4b7
Create Date: 2026-08-26 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c5d9e8f2a4b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    feature_source_type = postgresql.ENUM(
        "CLASS",
        "SUBCLASS",
        "RACE",
        "SUBRACE",
        "BACKGROUND",
        "OTHER",
        "FEAT",
        name="feature_source_type",
        create_type=False,
    )

    op.create_table(
        "source_item_choice_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_type", feature_source_type, nullable=False, index=True),
        sa.Column(
            "class_id",
            sa.Integer(),
            sa.ForeignKey("classes.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "background_id",
            sa.Integer(),
            sa.ForeignKey("backgrounds.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("pick_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("pick_count >= 1", name="check_choice_group_pick_count_positive"),
    )

    op.create_table(
        "source_item_choice_options",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("source_item_choice_groups.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("quantity >= 1", name="check_choice_option_quantity_positive"),
    )


def downgrade() -> None:
    op.drop_table("source_item_choice_options")
    op.drop_table("source_item_choice_groups")
